"""Backends: one per provider, selected by name."""

from __future__ import annotations

import os

from ..models import ModelCatalog
from .anthropic import Anthropic
from .base import Backend
from .gemini import Gemini
from .ollama import Ollama
from .ollama_cloud import OllamaCloud
from .openai import OpenAI

_BACKENDS: dict[str, type[Backend]] = {
    cls.provider_name: cls
    for cls in (Anthropic, OpenAI, Gemini, Ollama, OllamaCloud)
}


def backend_for(provider: str, model: str, api_key: str | None = None,
                catalog: ModelCatalog | None = None) -> Backend:
    """Build the backend for a provider name.

    The key defaults to the environment variable the backend names, which
    Config loads from .env. The catalog defaults to the bundled model data.
    """
    cls = _BACKENDS.get(provider)
    if cls is None:
        supported = ", ".join(sorted(_BACKENDS))
        raise ValueError(
            f"unknown provider '{provider}', supported: {supported}"
        )
    if api_key is None and cls.api_key_env:
        api_key = os.environ.get(cls.api_key_env)
    return cls(model, api_key=api_key, catalog=catalog)


__all__ = [
    "Anthropic",
    "Backend",
    "Gemini",
    "Ollama",
    "OllamaCloud",
    "OpenAI",
    "backend_for",
]
