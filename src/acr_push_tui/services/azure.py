"Azure CLI integration for ACR operations."

from __future__ import annotations

import shlex
from dataclasses import dataclass
from typing import Callable, Iterable

from acr_push_tui.services.subprocess_runner import CommandError, CommandResult, run_command


class AzureCliError(RuntimeError):
    """Raised when Azure CLI calls fail."""


@dataclass(frozen=True)
class AcrRegistry:
    """ACR registry metadata."""

    name: str
    resource_group: str
    login_server: str


@dataclass(frozen=True)
class AccountInfo:
    """Azure account metadata."""

    tenant_id: str
    tenant_name: str
    account_name: str


def ensure_logged_in(
    on_output: Callable[[str], None] | None = None,
    on_command: Callable[[str], None] | None = None,
) -> None:
    """Ensure Azure CLI has an active login.

    Raises:
        AzureCliError: If not logged in.
    """
    try:
        args = ["az", "account", "show"]
        _emit_command(args, on_command)
        run_command(args, on_output=on_output)
    except CommandError as exc:
        raise AzureCliError("Azure CLI is not logged in.") from exc


def get_current_account(
    on_output: Callable[[str], None] | None = None,
    on_command: Callable[[str], None] | None = None,
) -> AccountInfo:
    """Fetch current Azure account information.

    Returns:
        AccountInfo with tenant and account details.

    Raises:
        AzureCliError: If the account cannot be read.
    """
    try:
        args = [
            "az",
            "account",
            "show",
            "--query",
            "{Tenant:tenantId,TenantName:tenantDisplayName,Account:name}",
            "-o",
            "tsv",
        ]
        _emit_command(args, on_command)
        result = run_command(args, on_output=on_output)
    except CommandError as exc:
        raise AzureCliError("Failed to read Azure account info.") from exc
    parts = _split_tsv_lines(result)
    if not parts or len(parts[0]) != 3:
        raise AzureCliError("Unexpected Azure account response.")
    return AccountInfo(tenant_id=parts[0][0], tenant_name=parts[0][1], account_name=parts[0][2])


def login_tenant(
    tenant_id: str,
    on_output: Callable[[str], None] | None = None,
    on_command: Callable[[str], None] | None = None,
) -> None:
    """Login to a specific tenant.

    Args:
        tenant_id: Tenant id to login to.

    Raises:
        AzureCliError: If login fails.
    """
    if not tenant_id:
        raise AzureCliError("Tenant id is required for login.")
    try:
        args = ["az", "login", "--tenant", tenant_id]
        _emit_command(args, on_command)
        run_command(args, on_output=on_output)
    except CommandError as exc:
        raise AzureCliError(f"Failed to login to tenant: {tenant_id}") from exc


def set_subscription(
    subscription: str | None,
    on_output: Callable[[str], None] | None = None,
    on_command: Callable[[str], None] | None = None,
) -> None:
    """Set Azure subscription if provided.

    Args:
        subscription: Subscription id or name.

    Raises:
        AzureCliError: If subscription cannot be set.
    """
    if not subscription:
        return
    try:
        args = ["az", "account", "set", "--subscription", subscription]
        _emit_command(args, on_command)
        run_command(args, on_output=on_output)
    except CommandError as exc:
        raise AzureCliError(f"Failed to set subscription: {subscription}") from exc


def list_registries(
    on_output: Callable[[str], None] | None = None,
    on_command: Callable[[str], None] | None = None,
) -> list[AcrRegistry]:
    """List available ACR registries.

    Returns:
        List of registries.

    Raises:
        AzureCliError: If listing fails.
    """
    try:
        args = [
            "az",
            "acr",
            "list",
            "--query",
            "[].{Name:name,RG:resourceGroup,LS:loginServer}",
            "-o",
            "tsv",
        ]
        _emit_command(args, on_command)
        result = run_command(args, on_output=on_output)
    except CommandError as exc:
        raise AzureCliError("Failed to list registries.") from exc
    registries: list[AcrRegistry] = []
    for line in _split_tsv_lines(result):
        if len(line) != 3:
            continue
        registries.append(AcrRegistry(name=line[0], resource_group=line[1], login_server=line[2]))
    return registries


def show_registry(
    acr_name: str,
    resource_group: str,
    on_output: Callable[[str], None] | None = None,
    on_command: Callable[[str], None] | None = None,
) -> AcrRegistry:
    """Fetch registry details.

    Args:
        acr_name: Registry name.
        resource_group: Resource group name.

    Returns:
        Registry metadata.

    Raises:
        AzureCliError: If registry is not found.
    """
    try:
        args = [
            "az",
            "acr",
            "show",
            "--name",
            acr_name,
            "--resource-group",
            resource_group,
            "--query",
            "{Name:name,RG:resourceGroup,LS:loginServer}",
            "-o",
            "tsv",
        ]
        _emit_command(args, on_command)
        result = run_command(args, on_output=on_output)
    except CommandError as exc:
        raise AzureCliError(f"Registry not found: {acr_name}") from exc
    parts = _split_tsv_lines(result)
    if not parts or len(parts[0]) != 3:
        raise AzureCliError("Unexpected registry response.")
    return AcrRegistry(name=parts[0][0], resource_group=parts[0][1], login_server=parts[0][2])


def login_registry(
    acr_name: str,
    on_output: Callable[[str], None] | None = None,
    on_command: Callable[[str], None] | None = None,
) -> None:
    """Login to registry using Azure CLI.

    Args:
        acr_name: Registry name.

    Raises:
        AzureCliError: If login fails.
    """
    try:
        args = ["az", "acr", "login", "--name", acr_name]
        _emit_command(args, on_command)
        run_command(args, on_output=on_output)
    except CommandError as exc:
        raise AzureCliError(f"Failed to login to registry: {acr_name}") from exc


def list_repositories(
    acr_name: str,
    on_output: Callable[[str], None] | None = None,
    on_command: Callable[[str], None] | None = None,
) -> list[str]:
    """List repositories within an ACR.

    Args:
        acr_name: Registry name.

    Returns:
        List of repository names.
    """
    args = ["az", "acr", "repository", "list", "--name", acr_name, "-o", "tsv"]
    _emit_command(args, on_command)
    result = run_command(args, on_output=on_output)
    return [line[0] for line in _split_tsv_lines(result) if line]


def list_tags(
    acr_name: str,
    repository: str,
    on_output: Callable[[str], None] | None = None,
    on_command: Callable[[str], None] | None = None,
) -> list[str]:
    """List tags for a repository.

    Args:
        acr_name: Registry name.
        repository: Repository name.

    Returns:
        List of tags.
    """
    args = [
        "az",
        "acr",
        "repository",
        "show-tags",
        "--name",
        acr_name,
        "--repository",
        repository,
        "-o",
        "tsv",
    ]
    _emit_command(args, on_command)
    result = run_command(args, on_output=on_output)
    return [line[0] for line in _split_tsv_lines(result) if line]


def _split_tsv_lines(result: CommandResult) -> list[list[str]]:
    lines = []
    for raw in result.stdout.splitlines():
        parts = [part.strip() for part in raw.split("\t") if part.strip()]
        if parts:
            lines.append(parts)
    return lines


def _emit_command(args: list[str], on_command: Callable[[str], None] | None) -> None:
    if on_command:
        formatted = " ".join(shlex.quote(arg) for arg in args)
        on_command(formatted)
