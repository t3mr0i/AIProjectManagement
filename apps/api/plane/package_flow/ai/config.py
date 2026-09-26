# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Central LLM configuration — the single place every AI feature reads from.

Values come from the instance configuration (admin → AI) and fall back to the
environment. Supported ``LLM_PROVIDER`` values:

* ``openai`` — OpenAI API (``LLM_BASE_URL`` optional, e.g. Azure/proxy)
* ``anthropic`` — native Anthropic Messages API
* ``gemini`` — Google Gemini through its OpenAI-compatible endpoint
* ``ollama`` — local models through Ollama's OpenAI-compatible endpoint (no key)
* ``openai_compatible`` — any other OpenAI-compatible server (``LLM_BASE_URL`` required)

There is no model allow-list: providers publish new models faster than a
hard-coded list can follow, so any model name is passed through.
"""

import os
from dataclasses import dataclass

PROVIDER_PRESETS = {
    "openai": {
        "label": "OpenAI",
        "default_model": "gpt-4o-mini",
        "base_url": None,
        "needs_key": True,
        "embedding_model": "text-embedding-3-small",
    },
    "anthropic": {
        "label": "Anthropic",
        "default_model": "claude-opus-5",
        "base_url": None,
        "needs_key": True,
        # Anthropic has no embeddings endpoint; retrieval falls back to full-text search.
        "embedding_model": "",
    },
    "gemini": {
        "label": "Google Gemini",
        "default_model": "gemini-2.5-flash",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "needs_key": True,
        "embedding_model": "text-embedding-004",
    },
    "ollama": {
        "label": "Ollama (local)",
        "default_model": "llama3.1",
        "base_url": "http://localhost:11434/v1",
        "needs_key": False,
        "embedding_model": "nomic-embed-text",
    },
    "openai_compatible": {
        "label": "OpenAI-compatible",
        "default_model": "",
        "base_url": None,
        "needs_key": False,
        "embedding_model": "",
    },
}

# Legacy provider names from the upstream AI assistant.
_ALIASES = {"azure": "openai", "google": "gemini", "claude": "anthropic", "local": "ollama"}

CONFIG_KEYS = ("LLM_API_KEY", "LLM_PROVIDER", "LLM_MODEL", "LLM_BASE_URL", "LLM_EMBEDDING_MODEL")


@dataclass(frozen=True)
class LLMConfig:
    provider: str = "openai"
    model: str = ""
    api_key: str = ""
    base_url: str = ""
    embedding_model: str = ""

    @property
    def preset(self) -> dict:
        return PROVIDER_PRESETS.get(self.provider, PROVIDER_PRESETS["openai_compatible"])

    @property
    def is_configured(self) -> bool:
        """A real LLM can be called (otherwise the offline rule-based provider runs)."""
        if not self.model:
            return False
        if self.preset["needs_key"] and not self.api_key:
            return False
        if self.provider == "openai_compatible" and not self.base_url:
            return False
        return True

    @property
    def supports_embeddings(self) -> bool:
        return self.is_configured and bool(self.embedding_model)

    def public(self) -> dict:
        """Safe to show to users: never includes the key."""
        return {
            "provider": self.provider,
            "provider_label": self.preset["label"],
            "model": self.model,
            "configured": self.is_configured,
            "embeddings": self.supports_embeddings,
            "embedding_model": self.embedding_model if self.supports_embeddings else "",
        }


def normalize_provider(value) -> str:
    key = str(value or "openai").strip().lower().replace("-", "_")
    key = _ALIASES.get(key, key)
    return key if key in PROVIDER_PRESETS else "openai_compatible"


def build_config(*, provider=None, model=None, api_key=None, base_url=None, embedding_model=None) -> LLMConfig:
    provider = normalize_provider(provider)
    preset = PROVIDER_PRESETS[provider]
    embedding = embedding_model if embedding_model is not None else preset["embedding_model"]
    return LLMConfig(
        provider=provider,
        model=(model or preset["default_model"] or "").strip(),
        api_key=(api_key or "").strip(),
        base_url=(base_url or preset["base_url"] or "").strip(),
        embedding_model=(embedding or "").strip(),
    )


def _instance_values():
    try:
        from plane.license.utils.instance_value import get_configuration_value

        return get_configuration_value([{"key": key, "default": os.environ.get(key, "")} for key in CONFIG_KEYS])
    except Exception:  # configuration store unavailable (e.g. before migrations)
        return tuple(os.environ.get(key, "") for key in CONFIG_KEYS)


def load_config() -> LLMConfig:
    """Instance configuration (``SKIP_ENV_VAR``) or environment, as for every Plane setting."""
    values = {key: value or "" for key, value in zip(CONFIG_KEYS, _instance_values())}
    return build_config(
        provider=values["LLM_PROVIDER"],
        model=values["LLM_MODEL"],
        api_key=values["LLM_API_KEY"],
        base_url=values["LLM_BASE_URL"],
        embedding_model=values["LLM_EMBEDDING_MODEL"] or None,
    )
