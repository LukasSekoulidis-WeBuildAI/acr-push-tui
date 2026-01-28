# Usage

## Interactive TUI

The TUI uses a tree-based flow. Use arrow keys to move between nodes and Enter to expand the next level. Esc exits.

```
acr-push-tui run
```

## CI Mode

CI mode requires explicit flags for all required settings. Missing values will fail fast.

```
acr-push-tui run --ci \
  --acr myregistry \
  --rg my-resource-group \
  --repo myapp \
  --tag 1.0.0 \
  --dockerfile ./Dockerfile \
  --context .
```

## Environment Variables

All settings can be provided via environment variables with the `ACR_PUSH_` prefix. Example:

```
ACR_PUSH_ACR_NAME=
ACR_PUSH_ACR_RESOURCE_GROUP=
ACR_PUSH_REPO_NAME=
ACR_PUSH_TAG=
ACR_PUSH_DOCKERFILE_PATH=
ACR_PUSH_BUILD_CONTEXT=
ACR_PUSH_SKIP_LATEST=
ACR_PUSH_PLATFORM=
ACR_PUSH_LOG_LEVEL=
```
