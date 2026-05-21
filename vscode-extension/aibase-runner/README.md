# AI Base Runner

A VS Code / code-server extension that submits Python files, selected snippets,
and Jupyter cells to the **AI Base GPU cluster** instead of running them in the
local CPU kernel. Live output streams back into the editor.

## Commands

| Command | Default trigger |
|---------|-----------------|
| `AI Base: Run on GPU` | Right-click in `.py` / `.sh` editor |
| `AI Base: Run Selection on GPU` | Right-click when text is selected |
| `AI Base: Run Notebook Cell on GPU` | Run button on each Jupyter cell |
| `AI Base: Stop Current Job` | Command palette |
| `AI Base: Pick GPU Node` | Command palette |
| `AI Base: Pick Framework Image` | Command palette |
| `AI Base: Show Output Panel` | Click the status-bar item |

## Configuration

| Setting | Default |
|---------|---------|
| `aibase.serviceLayerUrl` | `http://job-scheduler:8000` |
| `aibase.framework` | `aibase/pytorch:2026-spring` |
| `aibase.preferredNode` | `auto` |
| `aibase.heartbeatIntervalSeconds` | `300` |

## How it works

1. The extension reads the user's JWT from `AIBASE_JWT_TOKEN` (injected by the
   Lab Manager when launching code-server). On first activation in dev mode it
   prompts for one and stores it in VS Code's SecretStorage.
2. When a Run command fires, the relevant content is compiled into a single
   shell script (Python cells wrapped in a heredoc, shell cells inlined) and
   submitted to `POST /api/v1/jobs` along with the selected framework image and
   preferred node.
3. The extension opens an SSE connection to `/api/v1/jobs/{job_id}/stream` and
   pipes the log lines into the **AI Base GPU** output channel. Progress
   percentage flows into the status-bar item.
4. A background heartbeat hits `POST /api/v1/lab/heartbeat` every 5 minutes so
   the Lab Manager keeps the editor session alive.

## Build

```bash
npm install
npm run compile
npx @vscode/vsce package -o aibase-runner.vsix
```

The base image `aibase/code-server` includes this extension pre-built.
