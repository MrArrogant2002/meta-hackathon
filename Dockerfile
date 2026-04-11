FROM python:3.12-slim

RUN useradd -m -u 1000 appuser

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY baseline/ ./baseline/
COPY server/ ./server/
COPY inference.py .
COPY openenv.yaml .
COPY README.md .

EXPOSE 7860

USER appuser

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]

