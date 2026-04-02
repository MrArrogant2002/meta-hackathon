---
title: SQL Query Debugging & Optimization Environment
emoji: 🗄️
colorFrom: blue
colorTo: green
sdk: docker
pinned: false
tags:
  - openenv
  - sql
  - reinforcement-learning
  - agent-environment
  - debugging
license: mit
---

# SQL Query Debugging & Optimization Environment

An [OpenEnv](https://github.com/huggingface/openenv)-compliant environment where AI agents learn to debug and optimize SQL queries — a skill every data engineer needs daily.

## Environment Description

Agents interact with a live SQLite database and must fix increasingly difficult SQL problems:

| Task | Difficulty | Problem | Reward Threshold |
|------|-----------|---------|-----------------|
| `easy_syntax_fix` | Easy | Missing `FROM` keyword | 0.8 |
| `medium_logic_fix` | Medium | Aggregate function in `WHERE` (should be `HAVING`) | 0.8 |
| `hard_optimization` | Hard | 4× correlated subqueries → single `JOIN + GROUP BY` | 0.7 |

## Database Schema

```sql
customers(id, name, age, city, email)
orders(id, customer_id, amount, product, status, created_at)
employees(id, name, department, salary, manager_id)
```

## Action Space

```json
{
  "sql_query": "string (required) — the SQL query to submit",
  "explanation": "string (optional) — agent's reasoning"
}
```

## Observation Space

| Field | Type | Description |
|-------|------|-------------|
| `task_id` | string | Current task identifier |
| `task_description` | string | What needs to be fixed |
| `broken_query` | string | The original broken SQL |
| `schema_info` | string | Database schema reference |
| `error_message` | string\|null | SQL error from last submission |
| `last_submission` | string\|null | Agent's previous query |
| `last_execution_result` | object\|null | Rows/columns from last execution |
| `hint` | string\|null | Contextual hint (appears after step 2) |
| `step_number` | int | Current step in episode |
| `max_steps` | int | Maximum steps before timeout |
| `done` | bool | Whether episode is terminal |

## Reward Function

Rewards provide dense partial-credit signals throughout the episode:

- **Easy task**: syntax_valid (0.25) + runs_without_error (0.25) + correct_keyword_fix (0.25) + correct_result (0.25)
- **Medium task**: syntax_valid (0.15) + runs_without_error (0.25) + uses_having (0.20) + no_aggregate_in_where (0.15) + correct_result (0.25)
- **Hard task**: runs_without_error (0.15) + correct_result (0.25) + no_correlated_subqueries (0.20) + uses_join (0.15) + uses_group_by (0.10) + subquery_free_bonus (0.15)

Step reward = `current_score - previous_best_score` (delta reward — rewards improvement).
Efficiency bonus: up to +0.2 for solving early in the episode.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/reset` | Start new episode, returns `session_id` + initial observation |
| POST | `/step` | Submit SQL action (pass `session_id` via `X-Session-Id` header) |
| GET | `/state` | Full trajectory history |
| GET | `/tasks` | All tasks with action schema |
| POST | `/grader` | Final grader score for a session |
| POST | `/baseline` | Run deterministic baseline, returns reproducible scores |
| GET | `/health` | Health check |

## Project Structure

```
.
├── Dockerfile               # Container config (port 7860, single worker)
├── pyproject.toml           # Project metadata, dependencies, entry point
├── uv.lock                  # Locked dependency versions (uv)
├── requirements.txt         # pip-compatible dependency list
├── openenv.yaml             # OpenEnv spec metadata
├── inference.py             # LLM baseline script (repo root, required by validator)
├── app/
│   ├── main.py              # FastAPI app + all endpoints
│   ├── environment.py       # reset / step / state logic
│   ├── models.py            # Pydantic typed models
│   ├── database.py          # SQLite schema + seed data
│   ├── tasks.py             # Task definitions + graders
│   └── session_store.py     # Thread-safe in-memory session management
├── baseline/
│   ├── inference.py         # LLM baseline (importable module)
│   └── rule_based.py        # Deterministic rule-based solver
└── server/
    └── app.py               # Entry point for multi-mode deployment
```

## Setup & Usage

### Local (pip)

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 7860 --workers 1
```

### Local (uv)

```bash
uv sync
uv run server
```

### Docker

```bash
docker build -t sql-query-env .
docker run -p 7860:7860 sql-query-env
```

### Quick Start (Python)

```python
import requests

BASE = "http://localhost:7860"

# Start episode — task_id optional, defaults to easy_syntax_fix
r = requests.post(f"{BASE}/reset", json={"task_id": "easy_syntax_fix"})
data = r.json()
session_id = data["session_id"]
obs = data["observation"]
print("Broken query:", obs["broken_query"])

# Submit fix
headers = {"X-Session-Id": session_id}
r = requests.post(f"{BASE}/step",
    json={"sql_query": "SELECT id, name, city FROM customers WHERE age > 30 ORDER BY name;"},
    headers=headers)
result = r.json()
print(f"Score: {result['info']['grader_score']}")  # → 1.0
print(f"Solved: {result['info']['solved']}")         # → True
```

### LLM Baseline

```bash
export HF_TOKEN=your_hf_token

# From repo root
python inference.py --host http://localhost:7860 --model Qwen/Qwen2.5-Coder-7B-Instruct

# Or as module
python -m baseline.inference --host http://localhost:7860
```

## Baseline Scores

### LLM Agent — `Qwen/Qwen2.5-Coder-7B-Instruct`

| Task | Score | Steps | Solved |
|------|-------|-------|--------|
| easy_syntax_fix | 1.000 | 1 | ✅ |
| medium_logic_fix | 1.000 | 1 | ✅ |
| hard_optimization | 1.000 | 1 | ✅ |
| **Average** | **1.000** | **1** | |

To reproduce:
```bash
export HF_TOKEN=your_hf_token
python -m baseline.inference --host http://localhost:7860 --model Qwen/Qwen2.5-Coder-7B-Instruct
```

### Rule-Based Deterministic Agent

| Task | Score | Solved |
|------|-------|--------|
| easy_syntax_fix | 1.000 | ✅ |
| medium_logic_fix | 1.000 | ✅ |
| hard_optimization | 1.000 | ✅ |

To reproduce (no external dependencies): `POST /baseline`
