# Pre-Submission Checklist

## Required Passes

- `openenv validate` passes
- Docker builds successfully
- `/reset`, `/step`, and `/state` respond correctly
- `/baseline` runs deterministically
- `inference.py` is in the repo root
- `inference.py` uses the OpenAI client
- `inference.py` prints exact `[START]`, `[STEP]`, and `[END]` line formats
- Three tasks exist with easy, medium, and hard progression
- All grader scores and rewards stay in the `0.0-1.0` range

## Domain-Specific Checks

- Easy task refunds a clearly eligible damage case
- Medium task requires the correct missing-information request before troubleshooting
- Hard task escalates to `fraud_review` instead of issuing a direct refund
- Graders are deterministic and rule-based
- The hard task includes policy tension, urgency, and fraud risk

## Deployment Checks

- HF Space returns `200` on `POST /reset`
- Container runs on port `7860`
- Single-worker startup is used because session state is in-process

## Inference Environment Variables

- `HF_TOKEN`
- `MODEL_NAME`
- `API_BASE_URL`
