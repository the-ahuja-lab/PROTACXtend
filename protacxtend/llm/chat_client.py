"""
Free-form assistant chat for PROTACXtend (pi-style prompt loop).
================================================================

Streams plain-text replies from whichever backend is active (see
`protacxtend.llm.setup`). Uses only `requests` so it works with Ollama and
every OpenAI-compatible endpoint. The scientific engine itself stays
deterministic + LLM-gated via the existing decision layer/graph — this
module is the conversational front door.
"""

from __future__ import annotations

import json
from typing import Callable, Dict, List, Optional

import requests

from protacxtend.llm.providers import ProviderConfig, get_config, provider_health

SYSTEM_PROMPT = (
    "You are the PROTACXtend research assistant — an evidence-grounded system for "
    "targeted protein degradation (PROTAC) design. You talk to a computational "
    "biologist/chemist. Facts you may state: PROTACXtend retrieves literature/databases, "
    "designs component-aware PROTACs (warhead·linker·E3 ligand), models ternary-complex and "
    "ubiquitination feasibility, predicts DC50/Dmax, and ranks candidates with provenance and "
    "uncertainty. NEVER invent experimental results, model numbers, papers, or tool output — say "
    "what the platform can run and be honest about uncertainty. If the user wants an actual design "
    "run, suggest:  protacxtend run \"<objective>\" --llm-enabled   or open the TUI. "
    "Keep answers concise and scientific."
)


def _ollama_endpoint(cfg: ProviderConfig) -> str:
    return cfg.base_url.rstrip("/") + "/api/chat"


def _api_endpoint(cfg: ProviderConfig) -> str:
    base = cfg.base_url.rstrip("/")
    if not base.endswith("/chat/completions"):
        base += "/chat/completions"
    return base


def stream_text(messages: List[Dict[str, str]],
                cfg: Optional[ProviderConfig] = None,
                on_delta: Optional[Callable[[str], None]] = None,
                timeout_s: int = 300) -> str:
    """Stream a reply from the active backend. Returns the full text."""
    cfg = cfg or get_config()
    collected: List[str] = []
    if cfg.provider == "ollama":
        payload = {"model": cfg.model, "messages": messages,
                   "stream": True, "options": {"temperature": cfg.temperature, "num_ctx": cfg.num_ctx}}
        with requests.post(_ollama_endpoint(cfg), json=payload,
                           timeout=timeout_s, stream=True) as r:
            r.raise_for_status()
            for line in r.iter_lines(decode_unicode=True):
                if not line:
                    continue
                try:
                    chunk = json.loads(line).get("message", {}).get("content") or ""
                except json.JSONDecodeError:
                    continue
                if chunk:
                    collected.append(chunk)
                    if on_delta:
                        on_delta(chunk)
        return "".join(collected)

    # OpenAI-compatible (+ openai/openrouter/anthropic-compatible proxies)
    headers = {"Content-Type": "application/json"}
    if cfg.api_key:
        headers["Authorization"] = f"Bearer {cfg.api_key}"
    payload = {"model": cfg.model, "messages": messages, "stream": True,
               "temperature": cfg.temperature}
    url = _api_endpoint(cfg)

    def consume(session_payload: dict, stream: bool) -> str:
        parts: List[str] = []
        session_payload = dict(session_payload); session_payload["stream"] = stream
        with requests.post(url, json=session_payload, headers=headers,
                           timeout=timeout_s, stream=stream) as resp:
            resp.raise_for_status()
            if stream:
                for line in resp.iter_lines(decode_unicode=True):
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        delta = json.loads(data)["choices"][0]["delta"].get("content")
                    except Exception:
                        delta = None
                    if delta:
                        parts.append(delta)
                        if on_delta:
                            on_delta(delta)
                return "".join(parts)
            body = resp.json()
            return body["choices"][0]["message"]["content"] or ""

    try:
        text = consume(payload, stream=True)
        return text if text else consume(payload, stream=False)
    except requests.RequestException:
        return consume(payload, stream=False)  # plain reply fallback


def chat_one_shot(text: str, cfg: Optional[ProviderConfig] = None, on_delta=None) -> str:
    cfg = cfg or get_config()
    messages = [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text}]
    return stream_text(messages, cfg=cfg, on_delta=on_delta)


def backend_banner(cfg: Optional[ProviderConfig] = None) -> str:
    cfg = cfg or get_config()
    health = provider_health(cfg)
    state = "healthy" if health.get("ok") else "unreachable"
    return f"{cfg.provider} · {cfg.model} · {cfg.base_url} [{state}]"
