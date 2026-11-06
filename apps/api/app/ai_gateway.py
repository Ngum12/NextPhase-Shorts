"""Future AI-planner adapter; deliberately not enabled in Stage 1.

OpenAI-compatible chat completions contract can target MiMo/OpenRouter/others.
Never place AI_API_KEY in Expo or send raw secrets to the mobile application.
"""
import os
import httpx

class ProviderDisabled(RuntimeError):
    pass

async def chat_completion(system_text: str, user_text: str, *, max_tokens: int = 2000) -> str:
    provider = os.getenv("AI_PROVIDER", "disabled")
    key = os.getenv("AI_API_KEY", "")
    base = os.getenv("AI_BASE_URL", "")
    model = os.getenv("AI_MODEL", "")
    if provider == "disabled" or not (key and base and model):
        raise ProviderDisabled("AI provider not configured; baseline render remains available")
    if provider not in {"mimo", "openrouter", "compatible"}:
        raise ProviderDisabled("Unsupported AI provider")
    # Admin-owned configuration only. Reject arbitrary API endpoints from users.
    allowed = ("https://api.xiaomimimo.com/v1", "https://openrouter.ai/api/v1")
    if not (base.rstrip("/") in allowed):
        raise ProviderDisabled("API base URL not on allowlist; validate provider before use")
    body = {"model": model, "messages": [
        {"role": "system", "content": system_text},
        {"role": "user", "content": user_text}], "max_tokens": max_tokens}
    async with httpx.AsyncClient(timeout=45.0) as client:
        res = await client.post(base.rstrip("/") + "/chat/completions", json=body,
                                headers={"Authorization": "Bearer " + key})
        res.raise_for_status()
        result = res.json()
    return result["choices"][0]["message"]["content"]
