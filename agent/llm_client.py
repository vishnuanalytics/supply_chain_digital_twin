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
    )
    return resp.choices[0].message.content, config.GROQ_MODEL


def _call_openrouter(system: str, user: str, max_tokens: int) -> tuple[str, str]:
    from openai import OpenAI

    if not config.OPENROUTER_API_KEY:
        raise ProviderError("OPENROUTER_API_KEY not set")
    client = OpenAI(api_key=config.OPENROUTER_API_KEY, base_url="https://openrouter.ai/api/v1")
    resp = client.chat.completions.create(
        model=config.OPENROUTER_MODEL,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content, config.OPENROUTER_MODEL


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
        t0 = time.monotonic()
        try:
            content, model = fn(system, user, max_tokens)
            latency_ms = (time.monotonic() - t0) * 1000
            return LLMResult(content=content, provider=provider, model=model, latency_ms=round(latency_ms, 1))
        except Exception as exc:  # noqa: BLE001 - deliberately broad, this is a fallback chain
            errors.append(f"{provider}: {exc}")
            continue
    raise RuntimeError(f"All LLM providers failed: {'; '.join(errors)}")
