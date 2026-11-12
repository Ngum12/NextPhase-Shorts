FROM python:3.12-slim AS asr-build
RUN apt-get update && apt-get install -y --no-install-recommends git cmake g++ make ca-certificates && rm -rf /var/lib/apt/lists/*
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export GIT_SSL_CAINFO=/run/secrets/proxy_ca; fi; \
    git init /source && git -C /source fetch --depth=1 https://github.com/ggml-org/whisper.cpp.git a8d002cfd879315632a579e73f0148d06959de36 && \
    test "$(git -C /source rev-parse FETCH_HEAD)" = a8d002cfd879315632a579e73f0148d06959de36 && \
    git -C /source checkout --detach FETCH_HEAD
RUN cmake -S /source -B /build -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF \
    -DGGML_NATIVE=OFF -DGGML_OPENMP=OFF -DGGML_CUDA=OFF -DGGML_VULKAN=OFF -DGGML_BLAS=OFF \
    -DGGML_AVX=OFF -DGGML_AVX2=OFF -DGGML_FMA=OFF -DGGML_F16C=OFF -DGGML_AVX512=OFF \
    -DGGML_RPC=OFF -DGGML_BACKEND_DL=OFF -DWHISPER_CURL=OFF -DWHISPER_BUILD_TESTS=OFF && \
    cmake --build /build --config Release --target whisper-cli --parallel 2 && \
    mkdir -p /opt/nextphase-asr && cp /build/bin/whisper-cli /opt/nextphase-asr/whisper-cli && \
    cp /source/LICENSE /opt/nextphase-asr/LICENSE && \
    mkdir -p /opt/nextphase-asr/notices && \
    cp /source/examples/miniaudio.h /source/examples/stb_vorbis.c /opt/nextphase-asr/notices/ && \
    sha256sum /opt/nextphase-asr/whisper-cli | cut -d ' ' -f 1 > /opt/nextphase-asr/engine.sha256

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg ca-certificates fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
WORKDIR /srv
COPY requirements.txt .
# Optional trust bundle for development networks with a TLS-inspecting proxy.
# BuildKit mounts it only for this step; it is never copied into the image.
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then \
      PIP_CERT=/run/secrets/proxy_ca pip install --no-cache-dir pip==26.3 && \
      PIP_CERT=/run/secrets/proxy_ca pip install --no-cache-dir -r requirements.txt; \
    else pip install --no-cache-dir pip==26.3 && pip install --no-cache-dir -r requirements.txt; fi
COPY app ./app
RUN chmod -R a+rX /srv/app && useradd --create-home nextphase && mkdir -p /var/nextphase/media && chown -R nextphase:nextphase /var/nextphase
USER nextphase
EXPOSE 8000
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000","--no-proxy-headers"]

FROM runtime AS analysis-worker
COPY --from=asr-build /opt/nextphase-asr /opt/nextphase-asr

FROM runtime AS default
