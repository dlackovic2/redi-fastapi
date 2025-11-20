# Base image - Python 3.13 slim (minimalan)
FROM python:3.14-slim AS base

# Metadata
LABEL maintainer="dominik.lackovic1@gmail.com"
LABEL description="REDI FastAPI Diacritic Restoration Service"

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Radni direktorij u kontejneru
WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Kopiraj aplikacijski kod
COPY fast_redi.py main.py ./

# Kopiraj model fajlove (veliki fajlovi)
COPY models/ ./models/

# Expose port (ne otvara port automatski)
EXPOSE 8000

# Health check - Docker provjerava je li servis živ
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl --fail http://localhost:8000/health || exit 1

# Pokreni aplikaciju
CMD ["uvicorn", "main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--backlog", "100", \
     "--limit-concurrency", "100" \
     ]