FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /srv
COPY requirements.txt .
# Optional trust bundle for development networks with a TLS-inspecting proxy.
# BuildKit mounts it only for this step; it is never copied into the image.
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then \
      PIP_CERT=/run/secrets/proxy_ca pip install --no-cache-dir -r requirements.txt; \
    else pip install --no-cache-dir -r requirements.txt; fi
COPY app ./app
RUN chmod -R a+rX /srv/app && useradd --create-home nextphase && mkdir -p /var/nextphase/media && chown -R nextphase:nextphase /var/nextphase
USER nextphase
EXPOSE 8000
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]
