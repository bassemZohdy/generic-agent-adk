"""Multi-provider model resolution via ADK's LiteLlm integration.

Rules (in order):
- If ``name`` contains "/", the prefix is the provider: return
  ``LiteLlm(model=name, ...)`` with api_key/base_url passed through.
- Else if ``provider`` (case-insensitive) is "google", "gemini" or empty:
  return the bare ``name`` string (native Gemini path).
- Else: return ``LiteLlm(model=f"{provider}/{name}", ...)``.
"""

from __future__ import annotations

import logging
import os

from google.adk.models.lite_llm import LiteLlm

logger = logging.getLogger(__name__)

#: Environment-variable hints per provider, for docs and warnings.
PROVIDER_ENV_HINTS: dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "ollama": "OLLAMA_API_BASE",
    "groq": "GROQ_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "together_ai": "TOGETHERAI_API_KEY",
    "hosted_vllm": "",  # depends on base_url
    "azure": "AZURE_API_KEY",
}

#: Providers that stay on ADK's native Gemini path.
_NATIVE_PROVIDERS = {"google", "gemini", ""}

#: Providers already warned about (warn once per process).
_warned: set[str] = set()


def _maybe_warn(provider: str, api_key: str | None) -> None:
    """Warn once when a provider's hinted env var is unset and no key given."""
    env_var = PROVIDER_ENV_HINTS.get(provider)
    if (
        env_var
        and api_key is None
        and os.environ.get(env_var) is None
        and provider not in _warned
    ):
        _warned.add(provider)
        logger.warning(
            "Provider %s usually requires %s; it is not set", provider, env_var
        )


def resolve_model(
    name: str,
    *,
    provider: str = "google",
    api_key: str | None = None,
    base_url: str | None = None,
) -> "str | LiteLlm":
    """Resolve a model name to a native Gemini string or a LiteLlm instance.

    Args:
        name: Model name, optionally "provider/model".
        provider: Provider used when ``name`` carries no "/" prefix.
        api_key: Optional API key forwarded to LiteLlm.
        base_url: Optional base URL forwarded to LiteLlm.

    Returns:
        The bare model string for the native Gemini path, else a LiteLlm.
    """
    kwargs = {
        k: v for k, v in (("api_key", api_key), ("base_url", base_url)) if v is not None
    }

    if "/" in name:
        resolved_provider = name.split("/", 1)[0].lower()
        _maybe_warn(resolved_provider, api_key)
        return LiteLlm(model=name, **kwargs)

    if provider.lower() in _NATIVE_PROVIDERS:
        return name

    _maybe_warn(provider.lower(), api_key)
    return LiteLlm(model=f"{provider}/{name}", **kwargs)
