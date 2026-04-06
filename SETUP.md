# Setup Instructions for Validators & Developers

## For Hugging Face Spaces Deployment (Recommended for Hackathon)

1. **Deploy the Space** from this repository
2. **Configure HF_TOKEN as a Space Secret:**
   - Go to Space Settings → Variables and secrets
   - Add new secret:
     - Name: `HF_TOKEN`
     - Value: Your HuggingFace token from https://huggingface.co/settings/tokens
3. The inference script will automatically use the secret when running in the Space

## For Local Development & Testing

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Create .env file from template:**
   ```bash
   cp .env.example .env
   ```

3. **Edit .env and add your HF_TOKEN:**
   ```bash
   # .env file
   HF_TOKEN=your_actual_hf_token_here
   ```

4. **Start the environment server:**
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 7860 --workers 1
   ```

5. **Run inference (in another terminal):**
   ```bash
   python inference.py
   ```

## Pre-Submission Validation Checklist

✅ **OpenEnv validation passes:**
```bash
openenv validate
```

✅ **Docker builds successfully:**
```bash
docker build -t sql-debug-env .
```

✅ **Server responds to /reset:**
```bash
curl -X POST http://localhost:7860/reset -H "Content-Type: application/json" -d '{"task_id": "easy_syntax_fix"}'
```

✅ **Inference script runs without errors:**
```bash
python inference.py
```

✅ **All 3 tasks return scores in [0.0, 1.0]**

✅ **Output follows [START], [STEP], [END] format**

## Environment Variables Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| HF_TOKEN | **Yes** | - | HuggingFace API token for LLM inference |
| MODEL_NAME | No | Qwen/Qwen2.5-72B-Instruct | Model to use for inference |
| API_BASE_URL | No | https://router.huggingface.co/v1 | LLM API endpoint |
| ENV_HOST | No | http://localhost:7860 | Environment server URL |

## Troubleshooting

**Q: Inference script fails with authentication error**
- A: Make sure HF_TOKEN is set correctly in .env (local) or Space secrets (deployed)

**Q: Server not responding**
- A: Check that the server is running on port 7860: `curl http://localhost:7860/health`

**Q: Docker build fails**
- A: Ensure all files are present: app/, baseline/, openenv.yaml, requirements.txt

**Q: Scores are all 0.0**
- A: Check that the LLM API is accessible and HF_TOKEN is valid
