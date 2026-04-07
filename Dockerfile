FROM python:3.12-slim

# HF Spaces runs containers as uid 1000
RUN useradd -m -u 1000 appuser

WORKDIR /app

# Install dependencies first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/
COPY baseline/ ./baseline/
COPY inference.py .
COPY openenv.yaml .

# HF Spaces requires port 7860
EXPOSE 7860

USER appuser

# --workers 1 is required: sessions are stored in-process memory
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]
