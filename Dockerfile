# Multi-arch: builds unchanged on amd64 (your PC) and arm64 (Oracle Ampere).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

# Build deps for cryptography/psycopg wheels are not needed on the platforms we
# target, but curl is used by the container healthcheck fallback.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# Generous timeout and retries: PyPI reads time out often enough that a
# default-configured build fails intermittently on slower links.
RUN pip install --no-cache-dir --timeout 120 --retries 8 -r requirements.txt

COPY app ./app
COPY scripts ./scripts

RUN mkdir -p /data && useradd -r -u 10001 nudnik && chown -R nudnik:nudnik /srv /data
USER nudnik

ENV DATA_DIR=/data
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
