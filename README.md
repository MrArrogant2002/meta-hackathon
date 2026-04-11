---
title: Customer Support Escalation Desk
emoji: 🎧
colorFrom: blue
colorTo: green
sdk: docker
pinned: false
tags:
  - openenv
  - customer-support
  - escalation
  - policy
  - agent-environment
license: mit
---

# Customer Support Escalation Desk

An [OpenEnv](https://github.com/huggingface/openenv)-compliant environment where AI agents learn real customer support operations: deciding whether to refund, request more information, troubleshoot, escalate, or close a case under explicit business policy.

## Environment Description

This environment models the day-to-day workflow of support operations teams. The agent receives a customer case with structured metadata, policy snippets, conversation history, and account signals, then must choose the correct operational action.

The environment is designed to score policy correctness, not writing style. That makes it deterministic, reproducible, and suitable for automated agent evaluation.

## Tasks

| Task | Difficulty | Scenario | Threshold |
| --- | --- | --- | --- |
| `easy_refund_eligible` | Easy | Damaged delivery with photo evidence and valid refund window | 0.85 |
| `medium_missing_info_tech_issue` | Medium | Technical issue missing order id and product model; agent must request details before troubleshooting | 0.80 |
| `hard_policy_edge_case` | Hard | VIP exception request with active chargeback and replacement already in flight | 0.75 |

## Why This Domain Is Real-World Useful

- Support teams make these decisions every day across refunds, troubleshooting, verification, and escalation.
- The hard task is not just “be polite”; it requires policy-safe decision making under conflicting signals.
- Graders are deterministic because the policy facts, missing fields, and allowed actions are fixed.
- The environment naturally supports partial-credit rewards and multi-step resolution.

## Action Space

```json
{
  "decision": "refund | troubleshoot | escalate | close | request_info",
  "priority": "low | medium | high | urgent",
  "reason_codes": [
    "damaged_item",
    "technical_issue",
    "missing_information",
    "within_return_window",
    "policy_exception",
    "fraud_risk",
    "repeat_contact"
  ],
  "request_fields": [
    "order_id",
    "device_model",
    "photo_evidence",
    "delivery_date",
    "serial_number"
  ],
  "recommended_steps": [
    "confirm_power_source",
    "factory_reset",
    "check_tracking",
    "verify_account_email"
  ],
  "escalation_team": "none | billing_review | logistics_ops | technical_support | fraud_review | retention_desk",
  "customer_message": "optional short string"
}
```

## Observation Space

| Field | Type | Description |
| --- | --- | --- |
| `task_id` | string | Current task identifier |
| `case_id` | string | Deterministic case id |
| `task_description` | string | Goal for the current case |
| `conversation_history` | array | Customer and system messages so far |
| `customer_tier` | string | `standard`, `gold`, or `platinum` |
| `sentiment` | string | Coarse sentiment signal |
| `urgency` | string | Operational urgency level |
| `order_snapshot` | object | Order/account metadata, including chargeback and replacement flags |
| `policy_snippet` | string | Explicit policy text for the task |
| `known_facts` | array | Grounded facts already available to the agent |
| `missing_fields` | array | Required fields not yet collected |
| `phase` | string | `initial` or `final_resolution` |
| `feedback` | string or null | Feedback from the last action |
| `hint` | string or null | Hint that appears later in the episode |
| `step_number` | int | Current step number |
| `max_steps` | int | Maximum steps before timeout |
| `done` | bool | Whether the episode is terminal |
| `last_action_error` | string or null | Raw semantic action error if the last action was invalid |

## Reward and Grading

All grader scores and rewards stay in the `[0.0, 1.0]` range required by the hackathon.

### Easy

- `decision_correct`: `0.50`
- `reason_damaged_item`: `0.10`
- `reason_within_return_window`: `0.10`
- `priority_correct`: `0.10`
- `no_unnecessary_escalation`: `0.10`
- `no_unnecessary_request_info`: `0.10`

### Medium

Phase 1 asks for the right missing information. Phase 2 applies the correct troubleshooting path once the details are revealed.

- Phase 1 contributes `45%` of the overall score
- Phase 2 contributes `55%` of the overall score

### Hard

- `decision_escalate`: `0.30`
- `team_fraud_review`: `0.25`
- `priority_high`: `0.10`
- `reason_fraud_risk`: `0.10`
- `reason_policy_exception`: `0.05`
- `reason_repeat_contact`: `0.05`
- `no_direct_refund`: `0.10`
- `no_unnecessary_request_info`: `0.05`

### Step Reward

Step reward is `max(0, current_score - previous_best_score)` plus a small solve efficiency bonus of up to `0.15`. This produces meaningful partial progress without leaving the valid reward range.

## API Endpoints

| Method | Path | Description |
| --- | --- | --- |
| POST | `/reset` | Start a new episode and return `session_id` plus initial observation |
| POST | `/step` | Submit an action using `X-Session-Id` |
| GET | `/state` | Return current state plus trajectory history |
| GET | `/tasks` | List tasks and action schema |
| POST | `/grader` | Return final grader score for a session |
| POST | `/baseline` | Run deterministic rule-based baseline |
| GET | `/health` | Health check |

## Project Structure

```text
.
├── Dockerfile
├── pyproject.toml
├── requirements.txt
├── openenv.yaml
├── inference.py
├── app/
│   ├── main.py
│   ├── environment.py
│   ├── models.py
│   ├── session_store.py
│   └── tasks.py
├── baseline/
│   ├── inference.py
│   └── rule_based.py
└── server/
    └── app.py
```

## Setup and Usage

### Local

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 7860 --workers 1
```

### Docker

```bash
docker build -t customer-support-escalation-desk .
docker run -p 7860:7860 customer-support-escalation-desk
```

### Quick Start

```python
import requests

BASE = "http://localhost:7860"

reset = requests.post(f"{BASE}/reset", json={"task_id": "easy_refund_eligible"}).json()
session_id = reset["session_id"]

action = {
    "decision": "refund",
    "priority": "medium",
    "reason_codes": ["damaged_item", "within_return_window"],
    "request_fields": [],
    "recommended_steps": [],
    "escalation_team": "none"
}

result = requests.post(
    f"{BASE}/step",
    json=action,
    headers={"X-Session-Id": session_id},
).json()

print(result["info"]["grader_score"])
print(result["info"]["solved"])
```

## Baseline Scores

### Deterministic Rule-Based Baseline

| Task | Score | Solved |
| --- | --- | --- |
| `easy_refund_eligible` | `1.00` | Yes |
| `medium_missing_info_tech_issue` | `1.00` | Yes |
| `hard_policy_edge_case` | `1.00` | Yes |

This baseline is available at `POST /baseline` and does not require an external model.

### Validator-Facing LLM Inference

The root [inference.py](/home/eswarbalu/Desktop/meta-hackthon/inference.py) uses the OpenAI client and prints the required `[START]`, `[STEP]`, and `[END]` lines for all three tasks.

Required environment variables:

- `HF_TOKEN`
- `MODEL_NAME`
- `API_BASE_URL`

Optional:

- `ENV_HOST`

Run:

```bash
export HF_TOKEN=your_token_here
export MODEL_NAME=Qwen/Qwen2.5-72B-Instruct
export API_BASE_URL=https://router.huggingface.co/v1
python inference.py
```

