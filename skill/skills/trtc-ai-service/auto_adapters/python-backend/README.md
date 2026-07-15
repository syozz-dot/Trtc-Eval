# python-backend Adapter

Connect the conversation-core skeleton as a reverse proxy into a Python backend.

| Framework | Template | Default Target |
|:---|:---|:---|
| Flask    | `flask.py.tpl`    | `voice_agent_proxy.py` (Blueprint) |
| FastAPI  | `fastapi.py.tpl`  | `voice_agent_proxy.py` (APIRouter) |
| Django   | `django.py.tpl`   | `voice_agent_proxy/views.py` (function view) |

## Configuration

| Env Variable | Default | Description |
|:---|:---|:---|
| `SKELETON_BASE_URL` | `http://localhost:3000` | Skeleton address |
| `API_PREFIX`        | `/api/v1`             | Skeleton prefix |
| `ROUTE_PREFIX`      | `/voice-agent`         | Self-mounting path |

## Notes

- The Django template uses `@csrf_exempt`, suitable only for reverse proxy scenarios; for CSRF support, integrate DRF separately.
- The FastAPI template is based on `httpx.AsyncClient`, aligning with the skeleton's async pipeline.
