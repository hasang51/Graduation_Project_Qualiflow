FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_ENV=production

RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN useradd --create-home --shell /bin/bash qualiflow
USER qualiflow

COPY --chown=qualiflow:qualiflow requirements.txt ./
RUN pip install --user -r requirements.txt

COPY --chown=qualiflow:qualiflow . .

RUN sed -i 's/\r$//' /app/scripts/docker-entrypoint.sh \
    && chmod +x /app/scripts/docker-entrypoint.sh

ENV PATH="/home/qualiflow/.local/bin:${PATH}"

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz')" || exit 1

EXPOSE 8000

ENTRYPOINT ["/app/scripts/docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
