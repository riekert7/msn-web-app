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

# Gunicorn: longer timeout for approve/deny (Drive + Sheets + email)
CMD ["gunicorn", "-b", "0.0.0.0:8080", "--timeout", "120", "main:app"]

