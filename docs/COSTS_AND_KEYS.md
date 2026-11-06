# Costs, keys and owner inputs (researched 2026-11-06)

## Start without paying

- Codex/repo development: use your existing Codex access subject to its plan limits.
- FFmpeg: free/libre, installed locally or in Docker. HyperFrames: an optional later renderer, verify current license/version before integrating.
- Python, FastAPI, PostgreSQL, Expo/React Native: open-source code; cloud resources are NOT free at scale.
- Initial Stage 1 does not call any LLM. The `ai_gateway.py` file is an *unwired* extension point.
- Optional AI experiments: OpenRouter free variants (currently limited requests/day), Gemini API free tier subject to model availability/usage policy; don't send sensitive customer media to a free tier without understanding provider terms.
- MiMo-V2.6-Flash is a promising planning model but **MiMo API is usage-billed**; free access in OpenCode does not automatically include a production API quota.

## What the owner should prepare

**Now:** GitHub repo (prefer private until license reviewed), laptop with Node 22, Python 3.12, Docker Desktop or FFmpeg, Android device/emulator, 3-5 original sample videos you have rights to, and an email for test accounts. Do NOT paste secrets in prompts.

**Before production cloud deployment:** billing-enabled cloud account (compute/storage), domain + email/SMS/push choices, service billing budget and limits, organizational payment account/KYC as required, privacy policy and legal review, incident/support contacts.

**Optional later:** developer key to MiMo/OpenRouter/Gemini or local open-source model deployments; private object-storage credentials; MTN/Flutterwave/other payment merchant credentials after verification; push notification credentials.

## Approximate choices (verify latest published rates and availability)

- Xiaomi MiMo overseas real-time API: `mimo-v2.6-flash` $0.14 / 1M cache-miss input tokens and $0.28 / 1M output tokens on pricing page dated 2026-10-08. Batch API less expensive but asynchronous and not for interactive jobs.
- OpenRouter free-model API: limited to 50 free requests/day before qualifying purchased credits; not sustainable for a production business.
- Gemini API: selected models on free tier; may be used to improve provider products; use paid terms for private production data.
- Mobile Money via Flutterwave: documentation lists Rwanda MTN/Airtel and Cameroon MTN/Orange; verify merchant eligibility, local fee schedule, approval and renewal mechanics.
- App-store rules: Google Play and Apple generally require store billing for digital app features/subscriptions, except for applicable exceptions/region programs. Use compliant app-store billing or a separately reviewed web-based checkout; do NOT include a link to bypass required native billing.

## Crucial cost accounting

Instrument per job: source seconds, output seconds, AI tokens, GPU/CPU seconds, queue delay, object-storage GB-days, bytes egress, estimated total variable cost, failures/retries, payment fee and refunds. Do not price subscriptions until P50/P95 cost and usage distribution are measured. Implement hard monthly credit caps and per-account concurrency caps; **never promise unlimited AI edits** without cost evidence.

## Official URLs

- MiMo pricing: https://mimo.mi.com/docs/en-US/pricing
- MiMo first API call: https://mimo.mi.com/docs/en-US/quick-start/summary/first-api-call
- OpenRouter free: https://openrouter.ai/collections/free-models
- Gemini pricing: https://ai.google.dev/gemini-api/docs/pricing
- Flutterwave Mobile Money: https://www.flutterwave.com/rw/support/payment-methods/pay-with-mobile-money
- Google Play payments: https://support.google.com/googleplay/android-developer/answer/9858738
- Apple App Review: https://developer.apple.com/app-store/review/guidelines/
