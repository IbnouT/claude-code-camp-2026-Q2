"""Ollama Cloud backend: the local wire format behind a hosted endpoint."""

from __future__ import annotations

from .ollama import Ollama


class OllamaCloud(Ollama):
    provider_name = "ollama_cloud"
    api_key_env = "OLLAMA_API_KEY"

    BASE_URL = "https://ollama.com"

    def configure_host(self, host: str) -> None:
        """OllamaCloud keeps its fixed hosted URL; a host override is ignored."""
        return None

    def headers(self) -> dict[str, str]:
        return {
            "content-type": "application/json",
            "Authorization": f"Bearer {self.api_key or ''}",
        }
