"""Provider-agnostic LLM client with fallback across Groq -> OpenRouter -> Anthropic ->
Gemini (order configurable via LLM_PROVIDER_ORDER). Every node in the agent should call
`complete()` rather than talking to a provider SDK directly, so swapping models or
adding a new provider never touches node logic.

The Ask tab's sidebar model picker lets a user manually force one specific
provider/model instead of the automatic fallback chain - set via `set_override()`
around a single question's graph run (see ui/agent_runner.py). Uses a contextvars
ContextVar rather than a plain module global: Streamlit runs each browser session's
script in its own thread, and a plain global would leak one user's manual model choice
into a concurrent session's questions on a multi-user deployment (this app is deployed
on Streamlit Cloud, so that's a real scenario, not a hypothetical).
"""
import contextvars
import time
from dataclasses import dataclass

from langsmith import traceable

from . import config


@dataclass
class LLMResult:
    content: str
    provider: str
    model: str
    latency_ms: float


class ProviderError(Exception):
    pass


class EmptyContentError(ProviderError):
    """Raised when a provider returns a 200 with no usable content. Observed as a
    transient blip (a same-provider retry usually succeeds immediately after), unlike a
    missing key or rate limit which won't be fixed by retrying the same provider."""


@traceable(run_type="llm", name="groq")
def _call_groq(system: str, user: str, max_tokens: int, model: str | None = None) -> tuple[str, str]:
    from openai import OpenAI

    if not config.GROQ_API_KEY:
        raise ProviderError("GROQ_API_KEY not set")
    model = model or config.GROQ_MODEL
    client = OpenAI(api_key=config.GROQ_API_KEY, base_url="https://api.groq.com/openai/v1")
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0,
        max_tokens=max_tokens,
        # gpt-oss models on Groq spend part of max_tokens on a hidden reasoning channel
        # before the visible answer; "low" keeps that from starving short structured
        # outputs (JSON/Cypher/SQL) of their token budget. Ignored by non-reasoning models.
        extra_body={"reasoning_effort": "low"},
    )
    return resp.choices[0].message.content, model


@traceable(run_type="llm", name="openrouter")
def _call_openrouter(system: str, user: str, max_tokens: int, model: str | None = None) -> tuple[str, str]:
    # Uses raw HTTP rather than the openai SDK: OpenRouter's free-tier reasoning models
    # sometimes send leading whitespace/padding before the JSON body (likely a keep-alive
    # artifact while a slow reasoning-heavy model computes), which has been observed to
    # trip the openai SDK's response parsing with an opaque "'NoneType' object is not
    # subscriptable" error. Parsing the body ourselves sidesteps that entirely.
    import json
    import urllib.error
    import urllib.request

    if not config.OPENROUTER_API_KEY:
        raise ProviderError("OPENROUTER_API_KEY not set")
    model = model or config.OPENROUTER_MODEL

    body = json.dumps({
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0,
        "max_tokens": max_tokens,
    }).encode()
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = json.loads(resp.read().decode().strip())
    except urllib.error.HTTPError as exc:
        raise ProviderError(f"OpenRouter HTTP {exc.code}: {exc.read().decode()[:500]}") from exc

    if "error" in payload:
        raise ProviderError(f"OpenRouter error: {payload['error']}")
    return payload["choices"][0]["message"]["content"], model


@traceable(run_type="llm", name="anthropic")
def _call_anthropic(system: str, user: str, max_tokens: int, model: str | None = None) -> tuple[str, str]:
    import anthropic

    if not config.ANTHROPIC_API_KEY:
        raise ProviderError("ANTHROPIC_API_KEY not set")
    model = model or config.ANTHROPIC_MODEL
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    text = "".join(block.text for block in resp.content if block.type == "text")
    return text, model


@traceable(run_type="llm", name="gemini")
def _call_gemini(system: str, user: str, max_tokens: int, model: str | None = None) -> tuple[str, str]:
    # Raw HTTP (stdlib urllib), not the google-genai SDK - same reasoning as OpenRouter
    # above: one dependency-free code path per provider rather than pulling in a new
    # SDK for a single endpoint call.
    import json
    import urllib.error
    import urllib.request

    if not config.GEMINI_API_KEY:
        raise ProviderError("GEMINI_API_KEY not set")
    model = model or config.GEMINI_MODEL

    body = json.dumps({
        "contents": [{"parts": [{"text": user}]}],
        "systemInstruction": {"parts": [{"text": system}]},
        "generationConfig": {
            "temperature": 0,
            "maxOutputTokens": max_tokens,
            # Like Groq's reasoning_effort above: without this, gemini-3.6-flash spends
            # part of max_tokens on a hidden "thinking" pass before the visible answer -
            # confirmed directly (72 total tokens for a 2-token reply with thinking on,
            # 8 total with it off) - which would starve short structured JSON/Cypher/SQL
            # outputs of their budget exactly like the Groq gpt-oss models do.
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }).encode()
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        data=body,
        headers={"x-goog-api-key": config.GEMINI_API_KEY, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        raise ProviderError(f"Gemini HTTP {exc.code}: {exc.read().decode()[:500]}") from exc

    try:
        parts = payload["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts)
    except (KeyError, IndexError) as exc:
        raise ProviderError(f"Gemini returned an unexpected response shape: {payload}") from exc
    return text, model


_PROVIDER_FNS = {
    "groq": _call_groq,
    "openrouter": _call_openrouter,
    "anthropic": _call_anthropic,
    "gemini": _call_gemini,
}

# Models known to work for each provider, used by the sidebar's manual model picker
# (ui/sidebar.py) - not an exhaustive list of everything each provider offers, just the
# ones worth offering a user a one-click choice between. Groq's daily token quota is
# per-model (each entry here has its own independent 200k TPD budget on the free tier),
# so switching Groq models is a genuine way to get more headroom, not just a different
# model's behavior - unlike OpenRouter, whose free-tier rate limit is account-wide
# across every ":free" model, so switching OpenRouter models changes output quality but
# does NOT grant more free requests.
KNOWN_MODELS = {
    "groq": ["openai/gpt-oss-120b", "qwen/qwen3.8-27b", "openai/gpt-oss-20b"],
    "openrouter": [
        "nvidia/nemotron-3-super-120b-a12b:free",
        "nvidia/nemotron-3-ultra-550b-a55b:free",
        "qwen/qwen3.8-27b:free",
        "google/gemma-4-31b-it:free",
    ],
    "anthropic": ["claude-sonnet-5"],
    "gemini": ["gemini-3.6-flash"],
}

_override: contextvars.ContextVar[dict | None] = contextvars.ContextVar("llm_override", default=None)


def set_override(provider: str | None, model: str | None = None) -> contextvars.Token:
    """Forces every complete() call for the current context (one Streamlit script run,
    since LangGraph's synchronous .stream() never crosses threads mid-question) to use
    exactly this provider/model, bypassing the automatic fallback chain entirely.
    `provider=None` clears any override (the "Auto" choice in the UI). Returns a token
    for reset_override() - callers must always reset in a finally block so a manual
    pick from one question can't leak into the next."""
    return _override.set({"provider": provider, "model": model} if provider else None)


def reset_override(token: contextvars.Token) -> None:
    _override.reset(token)


@traceable(run_type="chain", name="llm_complete")
def complete(system: str, user: str, max_tokens: int = 1024) -> LLMResult:
    """Tries each configured provider in order, falling back to the next on any
    error (missing key, rate limit, timeout, provider outage). Raises RuntimeError
    only if every configured provider fails.

    If set_override() is active (a user manually picked a specific provider/model in
    the sidebar), that single provider/model is tried alone with NO cross-provider
    fallback - a deliberate choice: if you explicitly asked for "Groq: qwen3.8-27b",
    silently answering via Anthropic instead when it fails would defeat the point of
    picking one, and would hide exactly the "is this specific model actually up right
    now" signal a manual picker is usually used to find out.

    Decorated with @traceable (a no-op unless LANGSMITH_TRACING=true) so every LLM call -
    including failed fallback attempts - shows up as a nested span in LangSmith under
    whichever graph node called it, since LangGraph nodes already run inside a traced
    Runnable context when tracing is enabled.
    """
    override = _override.get()
    if override:
        provider_order = [override["provider"]]
        model_override = override.get("model")
    else:
        provider_order = config.LLM_PROVIDER_ORDER
        model_override = None

    errors = []
    for provider in provider_order:
        fn = _PROVIDER_FNS.get(provider)
        if fn is None:
            errors.append(f"{provider}: unknown provider")
            continue

        # Empty content has been observed to be a transient blip (an immediate retry
        # against the same provider usually succeeds), unlike a missing key or rate
        # limit which won't be fixed by retrying — so only that error gets a same-
        # provider retry before this provider is given up on for good.
        for attempt in range(2):
            t0 = time.monotonic()
            try:
                content, model = fn(system, user, max_tokens, model_override)
                if not content or not content.strip():
                    raise EmptyContentError(f"{provider} ({model}) returned empty content")
                latency_ms = (time.monotonic() - t0) * 1000
                return LLMResult(content=content, provider=provider, model=model, latency_ms=round(latency_ms, 1))
            except EmptyContentError as exc:
                if attempt == 0:
                    continue  # one immediate retry against the same provider
                errors.append(f"{provider}: {type(exc).__name__}: {exc} (after retry)")
            except Exception as exc:  # noqa: BLE001 - deliberately broad, this is a fallback chain
                errors.append(f"{provider}: {type(exc).__name__}: {exc}")
                break  # not a transient-empty-content case, move on to the next provider

    if override:
        raise RuntimeError(f"Manually selected {override['provider']} failed: {'; '.join(errors)}")
    raise RuntimeError(f"All LLM providers failed: {'; '.join(errors)}")
