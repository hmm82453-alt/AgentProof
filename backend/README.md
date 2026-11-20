# Delta Exfil Multi-Agent Backend

FastAPI backend for the five-agent extraction planner. Each agent has an
independent endpoint and can call an OpenAI-compatible model.

## Endpoints

| Agent | Endpoint |
| --- | --- |
| Map intel | `POST /api/agents/map-intel` |
| Risk | `POST /api/agents/risk` |
| Supply | `POST /api/agents/supply` |
| Operator | `POST /api/agents/operator` |
| Audit | `POST /api/agents/audit` |

Additional endpoints:

- `GET /api/health`
- `GET /api/maps`
- `GET /api/operators`
- `POST /api/runs`
- `GET /api/runs`
- `GET /api/runs/{run_id}`
- `GET /api/runs/{run_id}/events`
- `GET /api/runs/{run_id}/event-log`
- `GET /api/runs/{run_id}/snapshots`
- `POST /api/runs/{run_id}/cancel`
- `POST /api/runs/{run_id}/retry`
- `GET /docs`

The backend serves `../delta-agent-console.html` at `/`. When the HTML is opened
through this server, it automatically probes `/api/health` and switches to API
mode. Double-clicking the HTML file still uses the offline mock mode.

Server-managed runs are persisted in `runtime/runs.db`. The SSE endpoint pushes
agent states, inter-agent messages, round results and snapshot events while the
orchestrator is running. Completed runs remain available for history inspection
and replay.

## Setup

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Set `LLM_API_KEY`, `LLM_API_BASE`, and `LLM_MODEL` in `.env` if needed. The
provided defaults target DeepSeek's OpenAI-compatible endpoint:

```env
LLM_API_BASE=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
```

If no key is configured, every endpoint remains available with deterministic
tactical data.

## Run

```powershell
cd backend
.\start.ps1
```

Open <http://127.0.0.1:8000>. Use <http://127.0.0.1:8000/?mode=mock> to force
the browser-only simulation, or `?mode=api` to force server calls.

## Test

```powershell
cd backend
.\run-tests.ps1
```

## LLM response safety

The deterministic result is generated first and sent to the model as grounded
context. The model is instructed to return JSON with the same contract. Missing
top-level fields are backfilled by the grounded result. If the model fails and
`LLM_FALLBACK_TO_MOCK=true`, the endpoint returns the deterministic result and
marks its source as `mock-fallback`.
