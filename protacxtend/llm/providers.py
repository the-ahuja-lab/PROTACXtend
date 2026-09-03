"""
LLM provider registry — any API in backend or frontend (provider-agnostic).
==========================================================================

Replace Ollama/gpt-oss:20b with ANY API without touching the decision layer:

  - ollama            (local default; gpt-oss:20b)
  - openai            (OpenAI API)
  - openrouter        (aggregator — many models)
  - anthropic         (Claude)
  - google            (Gemini)
  - openai_compatible (vLLM, LM Studio, Groq, Together, DeepSeek, ... via base_url)

Every provider implements the same Protocol: return RAW text; the gateway
handles JSON extraction/repair + Pydantic validation + deterministic
fallback. Structured-output format hints are provider-specific best-effort;
validation is always ours.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol

logger = logging.getLogger("protacpilot.llm.providers")


# ── Configuration (env-driven; runtime overrides via backend API) ─────

@dataclass
class ProviderConfig:
    provider: str = "ollama"
    model: str = "gpt-oss:20b"
    base_url: str = "http://127.0.0.1:11434"     # ollama server
    api_key: str = ""
    num_ctx: int = 16384
    temperature: float = 0.0
    timeout_s: int = 300

    @staticmethod
    def from_env() -> "ProviderConfig":
        return ProviderConfig(
            provider=os.environ.get("PROTACPILOT_LLM_PROVIDER", "ollama"),
            model=os.environ.get("PROTACPILOT_LLM_MODEL", "gpt-oss:20b"),
            base_url=os.environ.get("PROTACPILOT_LLM_BASE_URL", "http://127.0.0.1:11435"),
            api_key=os.environ.get("PROTACPILOT_LLM_API_KEY", ""),
            num_ctx=int(os.environ.get("PROTACPILOT_LLM_NUM_CTX", "16384")),
            temperature=float(os.environ.get("PROTACPILOT_LLM_TEMPERATURE", "0")),
            timeout_s=int(os.environ.get("PROTACPILOT_LLM_TIMEOUT_S", "300")),
        )


# ── Persistent user config (~/.protacxtend/llm.json) ──────────────────
USER_CONFIG_PATH = Path(os.environ.get("PROTACXTEND_HOME", "~/.protacxtend")).expanduser() / "llm.json"


def load_user_config() -> Optional["ProviderConfig"]:
    """Saved provider choice (written by `protacxtend llm setup`). None if absent."""
    try:
        if USER_CONFIG_PATH.exists():
            data = json.loads(USER_CONFIG_PATH.read_text())
            keys = ("provider", "model", "base_url", "api_key", "num_ctx", "temperature", "timeout_s")
            return ProviderConfig(**{k: data[k] for k in keys if k in data})
    except Exception as exc:  # pragma: no cover - best-effort read
        logger.warning("could not read %s: %s", USER_CONFIG_PATH, exc)
    return None


# Runtime override (set via backend API); None = use env config
_runtime_config: Optional[ProviderConfig] = None


def get_config() -> ProviderConfig:
    if _runtime_config is not None:
        return _runtime_config
    if os.environ.get("PROTACPILOT_LLM_PROVIDER"):      # explicit env wins
        return ProviderConfig.from_env()
    saved = load_user_config()                            # `protacxtend llm setup`
    if saved is not None:
        return saved
    return ProviderConfig.from_env()


def set_runtime_config(config: ProviderConfig) -> None:
    """Override provider config at runtime (backend/frontend switch)."""
    global _runtime_config
    _runtime_config = config


def reset_runtime_config() -> None:
    global _runtime_config
    _runtime_config = None


# ── Provider protocol ─────────────────────────────────────────────────

class LLMProvider(Protocol):
    name: str

    def chat_raw(self, system: str, user: str, schema_json: Dict[str, Any],
                 config: ProviderConfig) -> str:
        """Return raw text; gateway validates. Raises on transport errors."""
        ...

    def list_models(self, config: ProviderConfig) -> List[str]:
        ...


# ── Ollama (local) ────────────────────────────────────────────────────

class OllamaProvider:
    """Ollama via its HTTP API (no python `ollama` package required)."""
    name = "ollama"

    def _host(self, config) -> str:
        base = config.base_url or "http://127.0.0.1:11434"
        if not base.startswith("http"):
            base = f"http://{base}"
        return base.rstrip("/")

    def chat_raw(self, system, user, schema_json, config):
        import requests
        payload = {
            "model": config.model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "format": schema_json,                    # native schema enforcement
            "options": {"temperature": config.temperature, "num_ctx": config.num_ctx},
        }
        resp = requests.post(self._host(config) + "/api/chat", json=payload,
                             timeout=config.timeout_s)
        resp.raise_for_status()
        return resp.json().get("message", {}).get("content", "")

    def list_models(self, config):
        import requests
        try:
            resp = requests.get(self._host(config) + "/api/tags", timeout=5)
            resp.raise_for_status()
            return [m.get("name") or m.get("model") for m in resp.json().get("models", [])]
        except Exception:
            return []


# ── OpenAI + OpenAI-compatible (OpenRouter, vLLM, Groq, DeepSeek, ...) ─

class OpenAICompatibleProvider:
    """OpenAI + every /v1-compatible endpoint via HTTP (requests only)."""
    name = "openai_compatible"

    def _base(self, config) -> str:
        base = (config.base_url or "https://api.openai.com/v1").rstrip("/")
        return base if base.endswith("/chat/completions") else base + "/chat/completions"

    def _headers(self, config) -> dict:
        headers = {"Content-Type": "application/json"}
        if config.api_key:
            headers["Authorization"] = f"Bearer {config.api_key}"
        return headers

    def chat_raw(self, system, user, schema_json, config):
        import requests
        payload = {
            "model": config.model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "temperature": config.temperature,
        }
        url = self._base(config)
        try:
            resp = requests.post(url, json={**payload, "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "structured_decision", "schema": schema_json, "strict": False},
            }}, headers=self._headers(config), timeout=config.timeout_s)
            if resp.status_code >= 400 and "response_format" in resp.text:
                raise RuntimeError("response_format rejected")
            resp.raise_for_status()
        except Exception:
            # Retry without response_format (some endpoints reject schema)
            resp = requests.post(url, json={**payload, "messages": [{"role": "system", "content": system + " Reply with JSON only."},
                                                                    {"role": "user", "content": user}],
                                            "temperature": config.temperature},
                                 headers=self._headers(config), timeout=config.timeout_s)
            resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"] or ""

    def list_models(self, config):
        import requests
        try:
            base = config.base_url or "https://api.openai.com/v1"
            base = base.rstrip("/")
            if base.endswith("/chat/completions"):
                base = base[: -len("/chat/completions")]
            resp = requests.get(base + "/models", headers=self._headers(config), timeout=10)
            resp.raise_for_status()
            return [m["id"] for m in resp.json().get("data", [])]
        except Exception:
            return []


class OpenRouterProvider(OpenAICompatibleProvider):
    name = "openrouter"

    def __init__(self):
        self._default_base = "https://openrouter.ai/api/v1"


class OpenAIProvider(OpenAICompatibleProvider):
    name = "openai"


# ── Anthropic ─────────────────────────────────────────────────────────

class AnthropicProvider:
    name = "anthropic"

    def chat_raw(self, system, user, schema_json, config):
        import anthropic
        client = anthropic.Anthropic(api_key=config.api_key, timeout=config.timeout_s)
        # Anthropic: no native JSON-schema enforcement for plain completions;
        # instruct JSON-only output; the gateway validates + repairs.
        resp = client.messages.create(
            model=config.model,
            max_tokens=4096,
            temperature=config.temperature,
            system=system + "\nReply with JSON only, matching the schema.",
            messages=[{"role": "user", "content": user}],
        )
        parts = [b.text for b in resp.content if getattr(b, "type", "") == "text"]
        return "".join(parts)

    def list_models(self, config):
        return []  # Anthropic model list requires account; leave empty


# ── Google Gemini ─────────────────────────────────────────────────────

class GoogleProvider:
    name = "google"

    def chat_raw(self, system, user, schema_json, config):
        import google.generativeai as genai
        genai.configure(api_key=config.api_key)
        model = genai.GenerativeModel(
            config.model,
            system_instruction=system + "\nReply with JSON only, matching the schema.",
        )
        resp = model.generate_content(
            user,
            generation_config=genai.types.GenerationConfig(
                temperature=config.temperature,
                response_mime_type="application/json",
            ),
        )
        return resp.text or ""

    def list_models(self, config):
        return []  # requires account enumeration


# ── Registry ──────────────────────────────────────────────────────────

PROVIDER_REGISTRY: Dict[str, LLMProvider] = {
    "ollama": OllamaProvider(),
    "openai": OpenAIProvider(),
    "openrouter": OpenRouterProvider(),
    "anthropic": AnthropicProvider(),
    "google": GoogleProvider(),
    "openai_compatible": OpenAICompatibleProvider(),
}


def get_provider(name: Optional[str] = None) -> LLMProvider:
    name = name or get_config().provider
    if name not in PROVIDER_REGISTRY:
        raise ValueError(f"Unknown provider '{name}'. Available: {sorted(PROVIDER_REGISTRY)}")
    return PROVIDER_REGISTRY[name]


def list_available_providers() -> List[str]:
    return sorted(PROVIDER_REGISTRY)


def provider_health(config: Optional[ProviderConfig] = None) -> Dict[str, Any]:
    """Lightweight connectivity check (model list, no inference)."""
    cfg = config or get_config()
    provider = get_provider(cfg.provider)
    try:
        models = provider.list_models(cfg)
        return {
            "provider": cfg.provider,
            "model": cfg.model,
            "base_url": cfg.base_url,
            "ok": True,
            "models": models[:20],
            "n_models": len(models),
        }
    except Exception as exc:
        return {"provider": cfg.provider, "model": cfg.model, "ok": False, "error": str(exc)[:200]}
