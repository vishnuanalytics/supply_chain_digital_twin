"""Provider-agnostic LLM client with fallback across Groq -> OpenRouter -> Anthropic
(order configurable via LLM_PROVIDER_ORDER). Every node in the agent should call
`complete()` rather than talking to a provider SDK directly, so swapping models or
adding a new provider never touches node logic.
"""
import time
from dataclasses import dataclass

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


def _call_groq(system: str, user: str, max_tokens: int) -> tuple[str, str]:
    from openai import OpenAI

    if not config.GROQ_API_KEY:
        raise ProviderError("GROQ_API_KEY not set")
    client = OpenAI(api_key=config.GROQ_API_KEY, base_url="https://api.groq.com/openai/v1")
    resp = client.chat.completions.create(
        model=config.GROQ_MODEL,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0,
        max_tokens=max_tokens,
        # gpt-oss models on Groq spend part of max_tokens on a hidden reasoning channel
        # before the visible answer; "low" keeps that from starving short structured
        # outputs (JSON/Cypher/SQL) of their token budget. Ignored by non-reasoning models.
        extra_body={"reasoning_effort": "low"},
    )
    return resp.choices[0].message.content, config.GROQ_MODEL


def _call_openrouter(system: str, user: str, max_tokens: int) -> tuple[str, str]:
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

    body = json.dumps({
        "model": config.OPENROUTER_MODEL,
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
    return payload["choices"][0]["message"]["content"], config.OPENROUTER_MODEL


def _call_anthropic(system: str, user: str, max_tokens: int) -> tuple[str, str]:
    import anthropic

    if not config.ANTHROPIC_API_KEY:
        raise ProviderError("ANTHROPIC_API_KEY not set")
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    resp = client.messages.create(
        model=config.ANTHROPIC_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    text = "".join(block.text for block in resp.content if block.type == "text")
    return text, config.ANTHROPIC_MODEL


_PROVIDER_FNS = {
    "groq": _call_groq,
    "openrouter": _call_openrouter,
    "anthropic": _call_anthropic,
}


def complete(system: str, user: str, max_tokens: int = 1024) -> LLMResult:
    """Tries each configured provider in order, falling back to the next on any
    error (missing key, rate limit, timeout, provider outage). Raises RuntimeError
    only if every configured provider fails.
    """
    errors = []
    for provider in config.LLM_PROVIDER_ORDER:
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
                content, model = fn(system, user, max_tokens)
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
    raise RuntimeError(f"All LLM providers failed: {'; '.join(errors)}")
