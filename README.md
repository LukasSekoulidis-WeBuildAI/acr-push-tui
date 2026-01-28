# acr-push-tui

Textual TUI for building and pushing Docker images to Azure Container Registry.

![Screenshot](image.png)

## Setup

Install dependencies with uv:

```
uv sync
```

Install globally (choose one):

```
pipx install -e .
```

```
uv tool install .
```

```
pip install --user .
```

Run the TUI:

```
acr-push-tui run
```

Run CI mode:

```
acr-push-tui run --ci --acr <name> --rg <group> --repo <repo> --tag <tag> --dockerfile <path> --context <dir>
```

## Environment Variables

See `.env.example` for supported variables.

## Documentation

Detailed usage is in `docs/usage.md`.
