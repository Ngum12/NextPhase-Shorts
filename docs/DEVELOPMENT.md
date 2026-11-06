# Development validation

Python 3.12, Node 22+ (current validation used Node 24.22.1), FFmpeg/ffprobe,
and no paid API keys are required. Use the existing isolated cloud checkout;
do not create a worktree unless specifically requested.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r apps/api/requirements-dev.txt
# Create ignored .env from .env.example; use a fresh random JWT_SECRET (>=32 chars).
mkdir -p .data
PYTHONPATH=apps/api .venv/bin/python -m pytest apps/api/tests -q
.venv/bin/python scripts/smoke_e2e.py
cd apps/mobile
npm ci --no-audit --no-fund
npm run typecheck
EXPO_OFFLINE=1 npx expo install --check
EXPO_NO_TYPESCRIPT_SETUP=1 EXPO_OFFLINE=1 npx expo export --platform android --output-dir .expo/android-export --max-workers 2
```

`expo export` builds Android JavaScript/Hermes assets, not an APK or device UI test.
`expo install --check` uses installed SDK metadata offline; it is not Expo Doctor
online validation. Never use `--force`/`--legacy-peer-deps` to hide peer conflicts.

## Docker / PostgreSQL

Normal development uses `docker compose up --build -d --wait`, followed by
`.venv/bin/python scripts/smoke_e2e.py --base-url http://localhost:8000`.
API has an HTTP healthcheck; worker starts after API schema initialization.
Application source is readable by the unprivileged container user even when the
checkout's files have private modes. The renderer still runs without root.

On managed machines with a TLS-inspecting proxy, retain the supplied Docker proxy
configuration and CA trust. The Dockerfile accepts an optional BuildKit secret
`proxy_ca` for pip. For this environment, use an ignored override like
`.data/compose-validation.yaml`:

```yaml
services:
  api:
    build:
      secrets: [proxy_ca]
    ports: !override
      - "127.0.0.1:8002:8000"
  worker:
    build:
      secrets: [proxy_ca]
secrets:
  proxy_ca:
    file: /etc/ssl/certs/ca-certificates.crt
```

```bash
docker compose -p nextphase-validation -f compose.yaml -f .data/compose-validation.yaml up -d --build --wait
.venv/bin/python scripts/smoke_e2e.py --base-url http://127.0.0.1:8002
docker compose -p nextphase-validation -f compose.yaml -f .data/compose-validation.yaml down
```

Use the environment's documented local Docker socket selector if inherited
contexts point elsewhere. This override binds only loopback and keeps native API
port 8000 available. The public CA bundle is mounted only during pip installation,
not copied into image layers; package/TLS verification stays enabled. Do not save
secret values in overrides. Never remove pre-existing volumes to rerun a test.

## Android manual acceptance (outstanding)

1. Use a compatible Expo Go/development client and record device model, OS and SDK.
2. Configure `EXPO_PUBLIC_API_URL` for the emulator (`10.0.2.2:8000`) or a reachable
   development host. Cloud localhost is not reachable from a physical phone.
3. Start API and worker as documented in README; start Metro using reachable
   development networking. Use only synthetic or consented footage on trusted
   development networks; production requires HTTPS.
4. Register/sign in, select a 5–10-second clip, choose a future style and duration,
   upload, observe queue completion, download/share and play the result.
5. Confirm 9:16, <=requested/source/60 seconds, clear failure states, and owner
   isolation. Record actual evidence; do not mark passed based on JS bundling.
