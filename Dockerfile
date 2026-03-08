FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Cloud Run provides PORT; default to 8080 for local runs
ENV PORT=8080

# Gunicorn entrypoint for the Flask app defined in main.py as `app`
CMD ["gunicorn", "-b", "0.0.0.0:8080", "main:app"]

