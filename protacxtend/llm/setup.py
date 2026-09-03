"""
LLM backend setup — the startup question: API or Ollama?
========================================================

Interactive (and scriptable) provider configuration for PROTACXtend.

    protacxtend llm setup          # interactive: API vs Ollama
    protacxtend llm --set-provider ollama --model llama3.1:8b --base-url http://127.0.0.1:11434

The choice is persisted to ~/.protacxtend/llm.json and honoured by every
consumer (CLI run --llm-enabled, backend API, TUI bridge, gateway) because
`protacxtend.llm.providers.get_config()` falls back to the saved file when
no PROTACPILOT_LLM_* env var is set.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List, Optional

from protacxtend.llm.providers import (
    ProviderConfig,
    USER_CONFIG_PATH,
    get_config,
    get_provider,
    provider_health,
    set_runtime_config,
)

# Presets offered for the "API" path (all speak the same /v1 shape here).
API_PRESETS: Dict[str, Dict[str, str]] = {
    "openai":      {"base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini"},
    "openrouter":  {"base_url": "https://openrouter.ai/api/v1", "model": "openai/gpt-4o-mini"},
    "groq":        {"base_url": "https://api.groq.com/openai/v1", "model": "llama-3.3-70b-versatile"},
    "deepseek":    {"base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat"},
    "self-hosted": {"base_url": "", "model": ""},  # vLLM / LM Studio / llama.cpp server
}

OLLAMA_DEFAULT_BASE = "http://127.0.0.1:11434"


# ── persistence ────────────────────────────────────────────────────────

def save_config(cfg: ProviderConfig) -> Path:
    USER_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "provider": cfg.provider,
        "model": cfg.model,
        "base_url": cfg.base_url,
        "api_key": cfg.api_key,
        "num_ctx": cfg.num_ctx,
        "temperature": cfg.temperature,
        "timeout_s": cfg.timeout_s,
    }
    USER_CONFIG_PATH.write_text(json.dumps(payload, indent=2) + "\n")
    os.chmod(USER_CONFIG_PATH, 0o600)
    return USER_CONFIG_PATH


def read_config() -> Dict[str, object]:
    cfg = get_config()
    health = provider_health(cfg)
    return {
        "config_file": str(USER_CONFIG_PATH) if USER_CONFIG_PATH.exists() else "",
        "provider": cfg.provider,
        "model": cfg.model,
        "base_url": cfg.base_url,
        "api_key_set": bool(cfg.api_key),
        "health": health,
    }


def apply_config(provider: str, model: str, base_url: str = "", api_key: str = "",
                 save: bool = True) -> ProviderConfig:
    """Validate a provider choice, commit it as the runtime config, persist it."""
    from protacxtend.llm.providers import PROVIDER_REGISTRY
    if provider not in PROVIDER_REGISTRY:
        raise ValueError(f"Unknown provider '{provider}'. Available: {sorted(PROVIDER_REGISTRY)}")
    cfg = ProviderConfig(provider=provider, model=model or get_config().model,
                         base_url=base_url or get_config().base_url,
                         api_key=api_key or get_config().api_key)
    # Light connectivity probe before persisting (never raises).
    probe = provider_health(cfg)
    if save:
        save_config(cfg)
    set_runtime_config(cfg)
    return cfg, probe  # type: ignore[return-value]


# ── model helpers ──────────────────────────────────────────────────────

def list_ollama_models(base_url: str) -> List[str]:
    try:
        cfg = ProviderConfig(provider="ollama", base_url=base_url or OLLAMA_DEFAULT_BASE)
        return get_provider("ollama").list_models(cfg)
    except Exception:
        return []


# ── interactive setup (the startup question) ───────────────────────────

def interactive_setup(ask=input, out=print) -> ProviderConfig:
    """Ask: API or Ollama → configure → persist → return active config."""
    out("")
    out("PROTACXtend LLM backend — pick one:")
    out("  [1] API (OpenAI / OpenRouter / Groq / DeepSeek / self-hosted vLLM)")
    out("  [2] Ollama (local model)")
    choice = ask("Backend [1/2]: ").strip().lower()

    cfg: Optional[ProviderConfig] = None
    if choice in ("2", "ollama", "local", "o"):
        out(f"\nOllama — looking for models at {OLLAMA_DEFAULT_BASE} …")
        models = list_ollama_models(OLLAMA_DEFAULT_BASE)
        if models:
            out("Available models:")
            for i, m in enumerate(models, 1):
                out(f"  [{i}] {m}")
            pick = ask("Model number (or paste a model name): ").strip()
            try:
                model = models[int(pick) - 1]
            except (ValueError, IndexError):
                model = pick or "llama3.1:8b"
        else:
            base = ask(f"Ollama not reachable at {OLLAMA_DEFAULT_BASE}. Base URL [{OLLAMA_DEFAULT_BASE}]: ").strip() or OLLAMA_DEFAULT_BASE
            model = ask("Model [llama3.1:8b]: ").strip() or "llama3.1:8b"
            models = list_ollama_models(base)
        cfg = ProviderConfig(provider="ollama", model=model,
                             base_url=OLLAMA_DEFAULT_BASE if list_ollama_models(OLLAMA_DEFAULT_BASE) else base)
    else:
        out("\nAPI — quick presets:")
        names = list(API_PRESETS)
        for i, n in enumerate(names, 1):
            d = API_PRESETS[n]
            hint = d["model"] if d["model"] else "custom endpoint"
            out(f"  [{i}] {n:<12} ({hint})")
        presets = names + ["custom"]
        pick = ask("Preset number, or provider name: ").strip().lower()
        key = presets[int(pick) - 1] if pick.isdigit() and 0 < int(pick) <= len(presets) else pick
        if key not in API_PRESETS:
            key = "self-hosted"
        preset = API_PRESETS[key]
        base_url = ask(f"Base URL [{preset['base_url'] or 'http://localhost:8000/v1'}]: ").strip() or preset["base_url"] or "http://localhost:8000/v1"
        model = ask(f"Model [{preset['model'] or 'your-model'}]: ").strip() or preset["model"] or "your-model"
        api_key = ask("API key (leave empty if none): ").strip()
        provider = "openrouter" if key == "openrouter" else ("openai" if key == "openai" else "openai_compatible")
        cfg = ProviderConfig(provider=provider, model=model, base_url=base_url, api_key=api_key)

    path = save_config(cfg)
    set_runtime_config(cfg)
    out(f"\nSaved to {path}")
    return cfg
