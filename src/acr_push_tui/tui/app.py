"Textual application for ACR build and push."

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, TypeVar

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal
from textual.events import Key
from textual.message import Message
from textual.widgets import Footer, Header, Input, RichLog, Static, Tree
from textual.widgets.tree import TreeNode

from acr_push_tui.services import azure
from acr_push_tui.settings import AppSettings
from acr_push_tui.workflow import BuildPlan, WorkflowError, build_and_push, validate_docker_paths

logger = logging.getLogger(__name__)
T = TypeVar("T")


class NodeKind:
    ROOT = "root"
    REGISTRY = "registry"
    REPOSITORY = "repository"
    REPOSITORY_CUSTOM = "repository_custom"
    TAG = "tag"
    TAG_CUSTOM = "tag_custom"
    DOCKERFILE = "dockerfile"
    DOCKERFILE_CUSTOM = "dockerfile_custom"
    CONTEXT = "context"
    CONTEXT_CUSTOM = "context_custom"
    CONTEXT_CURRENT = "context_current"
    CONFIRM = "confirm"


@dataclass(frozen=True)
class NodeMeta:
    kind: str
    value: str | None = None
    payload: object | None = None


@dataclass
class Selection:
    acr_name: str | None = None
    acr_resource_group: str | None = None
    registry_server: str | None = None
    repository: str | None = None
    tag: str | None = None
    dockerfile_path: Path | None = None
    build_context: Path | None = None


class BuildFinished(Message):
    """Message emitted when build finishes."""

    def __init__(self, success: bool, error: str | None = None) -> None:
        super().__init__()
        self.success = success
        self.error = error


class AcrPushApp(App[None]):
    """Textual UI for ACR build and push."""

    CSS = """
    Screen {
        align: center middle;
        background: black;
        color: #7a6ff0;
    }
    Header, Footer {
        background: black;
        color: #7a6ff0;
    }
    #container, #left, #right {
        background: black;
        color: #7a6ff0;
    }
    #container {
        width: 100%;
        height: 100%;
    }
    #body {
        height: 1fr;
    }
    #left {
        width: 1fr;
        height: 100%;
    }
    #right {
        width: 1fr;
        height: 100%;
    }
    #tree {
        height: 1fr;
        border: heavy white;
        background: black;
        color: white;
    }
    #tree .tree--cursor,
    #tree .tree--highlight,
    #tree .tree--highlight-line,
    #tree .tree--label,
    #tree .tree--guides-selected {
        color: white;
    }
    #tree .tree--highlight,
    #tree .tree--cursor,
    #tree .tree--highlight-line {
        background: white;
        color: black;
    }
    #log {
        height: 1fr;
        border: heavy #7a6ff0;
        background: black;
        color: #7a6ff0;
    }
    #input {
        height: 3;
        padding: 0 1;
        background: black;
        color: #7a6ff0;
    }
    #input:focus {
        color: white;
        border: heavy white;
    }
    #status {
        dock: bottom;
        height: 3;
        padding: 0 1;
        background: black;
        color: #7a6ff0;
    }
    """

    BINDINGS = [
        ("escape", "quit", "Quit"),
    ]

    def __init__(self, settings: AppSettings) -> None:
        super().__init__()
        self.settings = settings
        self.selection = Selection()
        self.tree_widget = Tree("ACR Push", id="tree")
        self.status = Static(id="status")
        self.input = Input(id="input")
        self.log_widget = RichLog(id="log")
        self.pending_kind: str | None = None
        self.pending_node: TreeNode | None = None
        self.pending_label: str | None = None
        self.account_info: azure.AccountInfo | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="container"):
            with Horizontal(id="body"):
                with Container(id="left"):
                    yield self.tree_widget
                    yield self.input
                    yield self.status
                with Container(id="right"):
                    yield self.log_widget
        yield Footer()

    def on_mount(self) -> None:
        self.input.display = False
        self.status.update("Loading registries...")
        self.tree_widget.root.data = NodeMeta(kind=NodeKind.ROOT)
        self._load_registries()
        self.tree_widget.root.expand()
        self.tree_widget.focus()

    def on_key(self, event: Key) -> None:
        if event.key == "enter" and self.tree_widget.has_focus:
            self._handle_tree_enter()
            event.prevent_default()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        value = event.value.strip()
        if not value or not self.pending_kind or not self.pending_node:
            return
        self.input.display = False
        self._apply_pending_input(value, self.pending_node, self.pending_kind)
        self.pending_kind = None
        self.pending_node = None
        self.input.value = ""
        self.tree_widget.focus()

    def on_build_finished(self, message: BuildFinished) -> None:
        if message.success:
            self.status.update("Build and push completed.")
            self._append_log("Build and push completed.")
        else:
            self.status.update(f"Build failed: {message.error}")
            self._append_log(f"Build failed: {message.error}")
        self.tree_widget.disabled = False

    def _set_status(self, text: str) -> None:
        self.status.update(text)

    def _load_registries(self) -> None:
        try:
            registries = self._with_azure_loading(
                lambda: self._fetch_registries(),
            )
        except azure.AzureCliError as exc:
            self._set_status(str(exc))
            return
        self._clear_node(self.tree_widget.root)
        self._set_root_label()
        for registry in registries:
            label = f"{registry.name} (rg: {registry.resource_group})"
            self.tree_widget.root.add(label, data=NodeMeta(kind=NodeKind.REGISTRY, payload=registry))
        self._set_status(self._tenant_status_text())
        self._focus_first_registry()

    def _handle_tree_enter(self) -> None:
        node = self.tree_widget.cursor_node
        if node is None:
            return
        self._collapse_unrelated_branches(node)
        if node.is_expanded and node.children:
            node.collapse()
            self._set_status("Collapsed.")
            return
        meta = self._node_meta(node)
        if meta.kind == NodeKind.REGISTRY:
            self._expand_registry(node, meta)
        elif meta.kind == NodeKind.REPOSITORY:
            self._expand_tags(node, meta)
        elif meta.kind == NodeKind.REPOSITORY_CUSTOM:
            self._prompt_input("Enter repository name", node, NodeKind.REPOSITORY_CUSTOM)
        elif meta.kind == NodeKind.TAG:
            self._expand_dockerfiles(node, meta)
        elif meta.kind == NodeKind.TAG_CUSTOM:
            self._prompt_input("Enter tag", node, NodeKind.TAG_CUSTOM)
        elif meta.kind == NodeKind.DOCKERFILE:
            self._expand_context(node, meta)
        elif meta.kind == NodeKind.DOCKERFILE_CUSTOM:
            self._prompt_input("Enter Dockerfile path", node, NodeKind.DOCKERFILE_CUSTOM)
        elif meta.kind == NodeKind.CONTEXT_CURRENT:
            self._select_context(Path.cwd(), node)
        elif meta.kind == NodeKind.CONTEXT_CUSTOM:
            self._prompt_input("Enter build context path", node, NodeKind.CONTEXT_CUSTOM)
        elif meta.kind == NodeKind.CONFIRM:
            self._start_build()

    def _expand_registry(self, node: TreeNode, meta: NodeMeta) -> None:
        registry = meta.payload
        if not isinstance(registry, azure.AcrRegistry):
            self._set_status("Registry selection invalid.")
            return
        self.selection.acr_name = registry.name
        self.selection.acr_resource_group = registry.resource_group
        self.selection.registry_server = registry.login_server
        try:
            repos = self._with_azure_loading(
                lambda: self._load_repositories(registry.name),
            )
            repos = self._with_loading(node, lambda: repos)
        except azure.AzureCliError as exc:
            self._set_status(str(exc))
            return
        self._clear_node(node)
        self._set_status("Loading latest tags for repositories...")
        for repo in repos:
            label = self._repo_label(repo)
            node.add(label, data=NodeMeta(kind=NodeKind.REPOSITORY, value=repo))
        node.add("Create new repository", data=NodeMeta(kind=NodeKind.REPOSITORY_CUSTOM))
        node.expand()
        self._set_status("Select a repository and press Enter to expand.")

    def _expand_tags(self, node: TreeNode, meta: NodeMeta) -> None:
        repository = meta.value or ""
        if not self.selection.acr_name:
            self._set_status("Registry selection missing.")
            return
        self.selection.repository = repository
        try:
            tags = self._with_azure_loading(
                lambda: self._load_tags(self.selection.acr_name or "", repository),
            )
            tags = self._with_loading(node, lambda: tags)
        except azure.AzureCliError:
            tags = []
        self._populate_tag_options(node, tags)

    def _expand_dockerfiles(self, node: TreeNode, meta: NodeMeta) -> None:
        tag = meta.value or ""
        self.selection.tag = tag
        self._clear_node(node)
        dockerfiles = self._with_loading(node, lambda: self._find_dockerfiles(Path.cwd()))
        for dockerfile in dockerfiles:
            node.add(str(dockerfile), data=NodeMeta(kind=NodeKind.DOCKERFILE, value=str(dockerfile)))
        node.add("Custom path", data=NodeMeta(kind=NodeKind.DOCKERFILE_CUSTOM))
        node.expand()
        self._set_status("Select a Dockerfile and press Enter to expand.")

    def _expand_context(self, node: TreeNode, meta: NodeMeta) -> None:
        path_value = meta.value or ""
        self.selection.dockerfile_path = Path(path_value)
        self._clear_node(node)
        node.add("Use current directory", data=NodeMeta(kind=NodeKind.CONTEXT_CURRENT))
        node.add("Custom path", data=NodeMeta(kind=NodeKind.CONTEXT_CUSTOM))
        node.expand()
        self._set_status("Select a build context and press Enter to expand.")

    def _select_context(self, context: Path, node: TreeNode) -> None:
        self.selection.build_context = context
        self._clear_node(node)
        node.add("Confirm build and push", data=NodeMeta(kind=NodeKind.CONFIRM))
        node.expand()
        self._set_status(self._summary_text())

    def _prompt_input(self, placeholder: str, node: TreeNode, kind: str) -> None:
        self.pending_kind = kind
        self.pending_node = node
        self.pending_label = str(node.label)
        node.label = f"{self.pending_label} [input]"
        self.tree_widget.refresh()
        self.input.placeholder = placeholder
        self.input.value = ""
        self.input.display = True
        self.input.focus()
        self._set_status(placeholder)

    def _apply_pending_input(self, value: str, node: TreeNode, kind: str) -> None:
        if self.pending_label:
            node.label = self.pending_label
            self.pending_label = None
        if kind == NodeKind.REPOSITORY_CUSTOM:
            node.label = value
            node.data = NodeMeta(kind=NodeKind.REPOSITORY, value=value)
            self._clear_node(node)
            node.expand()
            self.selection.repository = value
            self._populate_tag_options(node, [])
        elif kind == NodeKind.TAG_CUSTOM:
            node.label = value
            node.data = NodeMeta(kind=NodeKind.TAG, value=value)
            self._expand_dockerfiles(node, node.data)
        elif kind == NodeKind.DOCKERFILE_CUSTOM:
            node.label = value
            node.data = NodeMeta(kind=NodeKind.DOCKERFILE, value=value)
            self._expand_context(node, node.data)
        elif kind == NodeKind.CONTEXT_CUSTOM:
            node.label = value
            node.data = NodeMeta(kind=NodeKind.CONTEXT, value=value)
            self._select_context(Path(value), node)

    def _start_build(self) -> None:
        try:
            plan = self._build_plan()
        except WorkflowError as exc:
            self._set_status(str(exc))
            return
        self.tree_widget.disabled = True
        self._set_status("Building and pushing...")
        self.log_widget.clear()
        self._append_log("Starting build and push...")
        self._append_log(self._summary_text())
        self.run_worker(self._run_build, thread=True)

    def _run_build(self) -> None:
        try:
            plan = self._build_plan()
            build_and_push(
                plan,
                on_output=lambda line: self.call_from_thread(self._append_log, line),
                on_command=lambda cmd: self.call_from_thread(self._append_command, cmd),
            )
            self.post_message(BuildFinished(success=True))
        except WorkflowError as exc:
            self.post_message(BuildFinished(success=False, error=str(exc)))

    def _append_log(self, text: str) -> None:
        if text:
            self.log_widget.write(text)

    def _append_command(self, command: str) -> None:
        self.log_widget.write(f"$ {command}")

    def _build_plan(self) -> BuildPlan:
        dockerfile_path = self.selection.dockerfile_path or Path()
        build_context = self.selection.build_context or Path()
        validate_docker_paths(dockerfile_path, build_context)
        return BuildPlan(
            registry_server=self.selection.registry_server or "",
            repository=self.selection.repository or "",
            tag=self.selection.tag or "",
            dockerfile_path=dockerfile_path,
            build_context=build_context,
            skip_latest=self.settings.skip_latest,
            platform=self.settings.platform,
        )

    def _node_meta(self, node: TreeNode) -> NodeMeta:
        data = node.data
        if isinstance(data, NodeMeta):
            return data
        return NodeMeta(kind=NodeKind.ROOT)

    def _clear_node(self, node: TreeNode) -> None:
        for child in list(node.children):
            child.remove()

    def _collapse_unrelated_branches(self, node: TreeNode) -> None:
        self._collapse_siblings(node)
        self._collapse_other_branches(node)

    def _collapse_siblings(self, node: TreeNode) -> None:
        parent = node.parent
        if parent is None:
            return
        for sibling in parent.children:
            if sibling is not node and sibling.is_expanded:
                sibling.collapse()

    def _collapse_other_branches(self, node: TreeNode) -> None:
        for child in self.tree_widget.root.children:
            if child is node:
                continue
            if self._is_ancestor(child, node):
                continue
            if child.is_expanded:
                child.collapse()

    def _is_ancestor(self, ancestor: TreeNode, node: TreeNode) -> bool:
        current = node.parent
        while current is not None:
            if current is ancestor:
                return True
            current = current.parent
        return False

    def _set_root_label(self) -> None:
        if not self.account_info:
            self.tree_widget.root.label = "ACR Push"
            self.tree_widget.root.data = NodeMeta(kind=NodeKind.ROOT)
            return
        label = f"{self.account_info.tenant_name} - {self.account_info.account_name}"
        self.tree_widget.root.label = label
        self.tree_widget.root.data = NodeMeta(kind=NodeKind.ROOT)

    def _tenant_status_text(self) -> str:
        if not self.account_info:
            return "Select a registry and press Enter to expand."
        return (
            "Current tenant: "
            f"{self.account_info.tenant_name} ({self.account_info.tenant_id}). "
            "Select a registry and press Enter to expand."
        )

    def _focus_first_registry(self) -> None:
        for child in self.tree_widget.root.children:
            meta = self._node_meta(child)
            if meta.kind == NodeKind.REGISTRY:
                self.tree_widget.select_node(child)
                return

    def _summary_text(self) -> str:
        return (
            "Press Enter to confirm build and push. "
            f"Registry={self.selection.registry_server} "
            f"Repo={self.selection.repository} "
            f"Tag={self.selection.tag} "
            f"Dockerfile={self.selection.dockerfile_path} "
            f"Context={self.selection.build_context} "
            f"SkipLatest={self.settings.skip_latest} "
            f"Platform={self.settings.platform or 'default'}"
        )

    def _populate_tag_options(self, node: TreeNode, tags: list[str]) -> None:
        self._clear_node(node)
        for tag in self._build_tag_options(tags):
            if tag == "Custom tag":
                node.add(tag, data=NodeMeta(kind=NodeKind.TAG_CUSTOM))
            else:
                node.add(tag, data=NodeMeta(kind=NodeKind.TAG, value=tag))
        node.expand()
        self._set_status("Select a tag and press Enter to expand.")

    def _build_tag_options(self, tags: list[str]) -> list[str]:
        latest_semver = self._max_semver(tags)
        options: list[str] = []
        if latest_semver:
            options.extend(self._suggest_versions(latest_semver))
        else:
            options.extend(["0.0.1", "0.1.0", "1.0.0"])
        options.append("Custom tag")
        return options

    def _max_semver(self, tags: list[str]) -> str | None:
        max_version: tuple[int, int, int] | None = None
        for tag in tags:
            parts = tag.split(".")
            if len(parts) != 3 or not all(part.isdigit() for part in parts):
                continue
            version = (int(parts[0]), int(parts[1]), int(parts[2]))
            if max_version is None or version > max_version:
                max_version = version
        if max_version is None:
            return None
        return f"{max_version[0]}.{max_version[1]}.{max_version[2]}"

    def _suggest_versions(self, base: str) -> list[str]:
        major, minor, patch = (int(part) for part in base.split("."))
        return [f"{major}.{minor}.{patch + 1}", f"{major}.{minor + 1}.0", f"{major + 1}.0.0"]

    def _repo_label(self, repository: str) -> str:
        try:
            tags = self._with_azure_loading(lambda: azure.list_tags(self.selection.acr_name or "", repository))
        except azure.AzureCliError:
            return f"{repository} - unknown"
        latest_semver = self._max_semver(tags)
        suffix = latest_semver or "no-tags"
        return f"{repository} - {suffix}"

    def _with_loading(self, node: TreeNode, action: Callable[[], T]) -> T:
        original_label = str(node.label)
        node.label = f"{original_label} [loading]"
        self.tree_widget.refresh()
        try:
            return action()
        finally:
            node.label = original_label
            self.tree_widget.refresh()

    def _with_azure_loading(self, action: Callable[[], T]) -> T:
        self.tree_widget.loading = True
        try:
            return action()
        finally:
            self.tree_widget.loading = False

    def _fetch_registries(self) -> list[azure.AcrRegistry]:
        azure.ensure_logged_in(
            on_output=self._append_log,
            on_command=self._append_command,
        )
        self.account_info = azure.get_current_account(
            on_output=self._append_log,
            on_command=self._append_command,
        )
        azure.set_subscription(
            self.settings.subscription,
            on_output=self._append_log,
            on_command=self._append_command,
        )
        return azure.list_registries(
            on_output=self._append_log,
            on_command=self._append_command,
        )

    def _load_repositories(self, acr_name: str) -> list[str]:
        azure.login_registry(
            acr_name,
            on_output=self._append_log,
            on_command=self._append_command,
        )
        return azure.list_repositories(
            acr_name,
            on_output=self._append_log,
            on_command=self._append_command,
        )

    def _load_tags(self, acr_name: str, repository: str) -> list[str]:
        return azure.list_tags(
            acr_name,
            repository,
            on_output=self._append_log,
            on_command=self._append_command,
        )

    def _find_dockerfiles(self, root: Path) -> list[Path]:
        results: list[Path] = []
        for path in root.rglob("*"):
            if path.is_file() and (path.name == "Dockerfile" or path.suffix == ".dockerfile"):
                results.append(path)
        return sorted(results)
