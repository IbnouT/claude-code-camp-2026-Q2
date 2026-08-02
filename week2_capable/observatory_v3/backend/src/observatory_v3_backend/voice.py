"""Optional speech synthesis for evidence-backed Live agent thoughts."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import httpx


class VoiceUnavailableError(RuntimeError):
    """Voice is unavailable because its local capability is not configured."""


class VoiceSynthesisError(RuntimeError):
    """The configured speech service did not return usable audio."""


@dataclass
class VoiceService:
    """Synthesize one bounded thought through direct REST with a local cache."""

    endpoint: str
    api_key: str | None
    model: str
    voice: str
    cache_root: Path | None
    transport: httpx.AsyncBaseTransport | None = None
    max_characters: int = 400
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @property
    def available(self) -> bool:
        return bool(self.api_key and self.cache_root is not None)

    async def synthesize(self, text: str) -> bytes:
        if not self.available:
            raise VoiceUnavailableError("Live voice is not configured")
        excerpt = text.strip()[: self.max_characters]
        if not excerpt:
            raise VoiceUnavailableError("No Agent thinking excerpt is available")
        cache_path = self._cache_path(excerpt)
        if cache_path.is_file():
            return cache_path.read_bytes()
        async with self._lock:
            if cache_path.is_file():
                return cache_path.read_bytes()
            audio = await self._request_audio(excerpt)
            self._store(cache_path, audio)
            return audio

    def _cache_path(self, text: str) -> Path:
        assert self.cache_root is not None
        identity = json.dumps(
            {
                "model": self.model,
                "voice": self.voice,
                "text": text,
            },
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
        digest = hashlib.sha256(identity).hexdigest()
        return self.cache_root / f"{digest}.mp3"

    async def _request_audio(self, text: str) -> bytes:
        assert self.api_key is not None
        try:
            async with httpx.AsyncClient(
                transport=self.transport,
                timeout=20,
            ) as client:
                response = await client.post(
                    self.endpoint,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "voice": self.voice,
                        "input": text,
                        "response_format": "mp3",
                    },
                )
                response.raise_for_status()
        except httpx.HTTPError as error:
            raise VoiceSynthesisError(
                "The configured voice service is unavailable"
            ) from error
        if not response.content:
            raise VoiceSynthesisError(
                "The configured voice service returned empty audio"
            )
        return response.content

    def _store(self, target: Path, audio: bytes) -> None:
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            dir=target.parent,
            prefix=f".{target.stem}-",
            suffix=".tmp",
        )
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(audio)
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
