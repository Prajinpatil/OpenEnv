# mail_pro_env — OpenEnv Mail Classification & Routing

A production-ready, multi-tier email classification environment built on the
OpenEnv SDK. An LLM agent processes a queue of synthetic emails and must
classify or route each one correctly to earn rewards.

---

## Project Structure

```
envs/mail_pro_env/
├── models.py                  # Pydantic v2 models (MailAction, MailObservation, …)
├── openenv.yaml               # OpenEnv manifest
├── pyproject.toml             # uv-managed dependencies
├── Dockerfile                 # Multi-stage build (builder + runtime)
├── baseline_inference.py      # LLM agent runner
├── server/
│   ├── __init__.py
│   ├── environment.py         # MailEnv class + Grader
│   └── app.py                 # FastAPI HTTP wrapper
└── tests/
    └── test_environment.py    # pytest unit tests
```

---

## Task Tiers

| Tier   | Task                  | Labels                                        | Max reward/email |
|--------|-----------------------|-----------------------------------------------|-----------------|
| easy   | Spam Filter           | `Spam`, `Ham`                                 | 1.0             |
| medium | Priority Sorting      | `High`, `Medium`, `Low`                       | 1.0             |
| hard   | Department Routing    | `HR`, `Tech_Support`, `Billing`, `Legal`, `Sales` + priority | 1.5 |

### Partial Rewards (Hard Tier)
| Outcome                        | Reward |
|-------------------------------|--------|
| Correct department + priority  | 1.5    |
| Correct department only        | 1.0    |
| Correct priority only          | 0.5    |
| Both wrong                     | 0.0    |

---

## Quickstart (local, no Docker)

### 1. Install dependencies with `uv`

```bash
pip install uv          # if not already installed

cd envs/mail_pro_env
uv venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
uv pip install -e ".[dev]"
```

### 2. Validate the environment spec

```bash
openenv validate        # requires the openenv CLI to be installed
```

### 3. Run unit tests

```bash
pytest tests/ -v
```

### 4. Run the LLM baseline agent

```bash
# OpenAI backend (default)
export OPENAI_API_KEY=sk-...
python baseline_inference.py

# Filter to one tier
TASK_TIER=hard python baseline_inference.py

# HuggingFace backend
export BACKEND=hf
export HF_API_KEY=hf_...
export HF_ENDPOINT_URL=https://your-endpoint.huggingface.cloud
python baseline_inference.py
```

### 5. Start the HTTP server

```bash
uvicorn server.app:app --host 0.0.0.0 --port 8000 --reload
```

API endpoints:
- `POST /reset`  — start a new episode
- `POST /step`   — submit a classification action
- `GET  /state`  — inspect the full environment state (for replay)
- `GET  /health` — liveness probe

---

## Docker

### Build

```bash
docker build -t mail-pro-env:latest .
```

### Run the HTTP server

```bash
docker run -p 8000:8000 mail-pro-env:latest
```

### Run baseline inference inside the container

```bash
docker run \
  -e OPENAI_API_KEY=sk-... \
  -e TASK_TIER=all \
  --entrypoint python \
  mail-pro-env:latest \
  baseline_inference.py
```

---

## Environment Python API

```python
from server.environment import MailEnv
from models import MailAction

env = MailEnv()

# --- Reset ---------------------------------------------------------------
obs = env.reset(seed=42, task_tier="hard", shuffle=False)

# --- Step ----------------------------------------------------------------
while True:
    action = MailAction(label="Billing", priority="High", confidence=0.9)
    result = env.step(action)

    print(f"reward={result.reward:.2f}  done={result.done}")
    print(f"info={result.info}")

    if result.done:
        print(result.info["grader_report"])
        break
    obs = result.observation

# --- State (replay) -------------------------------------------------------
snapshot = env.state()           # JSON-serialisable dict
env2     = MailEnv.from_state(snapshot)   # reconstruct
```

---

## Reward Breakdown in `info`

Every `StepResult.info` dict contains:

```json
{
  "tier": "hard",
  "ground_truth": {"label": "Billing", "priority": "High"},
  "agent_label": "Billing",
  "agent_priority": "High",
  "dept_correct": true,
  "priority_correct": true,
  "reward_breakdown": {"dept_reward": 1.0, "priority_reward": 0.5}
}
```

On the **final step**, `info` also contains a `grader_report`:

```json
{
  "overall_score": 0.8667,
  "total_reward": 13.0,
  "max_possible_reward": 15.0,
  "total_emails": 10,
  "tier_breakdown": {
    "hard": {"emails_processed": 10, "score": 0.8667, ...}
  }
}
```

---

## Expanding the Dataset

The bundled dataset contains 23 synthetic emails (6 easy, 7 medium, 10 hard).
For a full hackathon challenge, expand to 50+ emails per tier in a separate
JSON file and load it in `server/environment.py`:

```python
import json, pathlib
_GOLDEN_EMAILS = json.loads(
    pathlib.Path("data/emails.json").read_text()
)
```

---

## Environment Variables

| Variable         | Default        | Description                              |
|-----------------|----------------|------------------------------------------|
| `OPENAI_API_KEY` | —              | Required for OpenAI backend              |
| `OPENAI_MODEL`   | `gpt-4o-mini`  | OpenAI model name                        |
| `HF_API_KEY`     | —              | Required for HuggingFace backend         |
| `HF_ENDPOINT_URL`| —              | HF inference endpoint URL                |
| `BACKEND`        | `openai`       | `openai` or `hf`                         |
| `TASK_TIER`      | `all`          | `easy`, `medium`, `hard`, or `all`       |
| `SEED`           | `42`           | Reproducibility seed                     |