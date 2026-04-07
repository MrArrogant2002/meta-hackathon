# Use fully qualified image with digest to avoid registry issues
FROM python@sha256:f966cda3c2d5b990db2a7af10ef891f5ca685c7d0c6a83378948f1cd09c27ecd

# HF Spaces runs containers as uid 1000
RUN useradd -m -u 1000 appuser

WORKDIR /app

# Install dependencies first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/
COPY baseline/ ./baseline/
COPY openenv.yaml .

# HF Spaces requires port 7860
EXPOSE 7860

USER appuser

# --workers 1 is required: sessions are stored in-process memory
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]
