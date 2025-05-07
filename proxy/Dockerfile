FROM python:3.12-slim

WORKDIR /app
COPY ollama_proxy.py .

RUN pip install --no-cache-dir flask requests gunicorn

EXPOSE 11434
CMD ["gunicorn", "--bind", "0.0.0.0:11434", "--workers", "1", "ollama_proxy:app"]
