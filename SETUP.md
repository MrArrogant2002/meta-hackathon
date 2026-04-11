# Setup Instructions for Validators and Developers

## 1. Install Dependencies

```bash
pip install -r requirements.txt
```

## 2. Run the Environment

```bash
uvicorn app.main:app --host 0.0.0.0 --port 7860 --workers 1
```

## 3. Optional Docker Run

```bash
docker build -t customer-support-escalation-desk .
docker run -p 7860:7860 customer-support-escalation-desk
```

## 4. Run the Deterministic Baseline

```bash
curl -X POST http://localhost:7860/baseline
```

## 5. Run Validator-Facing Inference

```bash
export HF_TOKEN=your_token_here
export MODEL_NAME=Qwen/Qwen2.5-72B-Instruct
export API_BASE_URL=https://router.huggingface.co/v1
python inference.py
```

## Environment Variables

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `HF_TOKEN` | Yes for `inference.py` | - | Token used by the OpenAI client |
| `MODEL_NAME` | No | `Qwen/Qwen2.5-72B-Instruct` | Model identifier for inference |
| `API_BASE_URL` | No | `https://router.huggingface.co/v1` | OpenAI-compatible inference endpoint |
| `ENV_HOST` | No | `http://localhost:7860` | Base URL of the environment |

## Validation Checks

- `openenv validate`
- `docker build -t customer-support-escalation-desk .`
- `POST /reset` returns `200`
- `POST /baseline` returns deterministic scores
- `python inference.py` prints only `[START]`, `[STEP]`, and `[END]` line types

## Hugging Face Spaces

Set these as Space secrets if you run `inference.py` in a deployed environment:

- `HF_TOKEN`
- `MODEL_NAME` if overriding the default
- `API_BASE_URL` if overriding the default router
