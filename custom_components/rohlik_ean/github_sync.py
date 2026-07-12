"""Backup/restore of the learned EAN database to a GitHub repository.

Uses the contents API (PUT /repos/{repo}/contents/{path}) — one JSON file,
one commit per (debounced) change. Identical content is not re-committed.
"""
from __future__ import annotations

import base64
import json
import logging

import aiohttp

_LOGGER = logging.getLogger(__name__)

API_URL = "https://api.github.com/repos/{repo}/contents/{path}"


class GitHubSyncError(Exception):
    """Backup/restore failed."""


class GitHubSync:
    """Minimal GitHub contents-API client for one JSON file."""

    def __init__(
        self, session: aiohttp.ClientSession, repo: str, token: str, path: str
    ) -> None:
        self._session = session
        self._repo = repo.strip().strip("/")
        self._token = token.strip()
        self._path = path.strip().lstrip("/")

    @property
    def configured(self) -> bool:
        return bool(self._repo and self._token and self._path)

    @property
    def _url(self) -> str:
        return API_URL.format(repo=self._repo, path=self._path)

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
        }

    async def _async_get(self) -> tuple[dict | None, str | None]:
        """Return (mappings, blob sha); (None, None) when the file is absent."""
        try:
            async with self._session.get(
                self._url,
                headers=self._headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as response:
                if response.status == 404:
                    return None, None
                if response.status != 200:
                    raise GitHubSyncError(
                        f"GitHub GET {self._path}: HTTP {response.status}"
                    )
                payload = await response.json()
        except aiohttp.ClientError as err:
            raise GitHubSyncError(f"GitHub unreachable: {err}") from err

        try:
            content = base64.b64decode(payload.get("content", "")).decode("utf-8")
            return json.loads(content), payload.get("sha")
        except (ValueError, UnicodeDecodeError) as err:
            raise GitHubSyncError(f"Invalid backup file content: {err}") from err

    async def async_fetch(self) -> dict | None:
        """Download the backed-up mappings; None when no backup exists."""
        mappings, _sha = await self._async_get()
        return mappings

    async def async_backup(self, mappings: dict) -> bool:
        """Commit the mappings; returns False when content was unchanged."""
        remote, sha = await self._async_get()
        if remote == mappings:
            return False

        content = json.dumps(mappings, ensure_ascii=False, indent=2, sort_keys=True)
        body: dict = {
            "message": f"rohlik_ean: backup ({len(mappings)} mappings)",
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        }
        if sha:
            body["sha"] = sha

        try:
            async with self._session.put(
                self._url,
                headers=self._headers,
                json=body,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as response:
                if response.status not in (200, 201):
                    text = (await response.text())[:200]
                    raise GitHubSyncError(
                        f"GitHub PUT {self._path}: HTTP {response.status} {text}"
                    )
        except aiohttp.ClientError as err:
            raise GitHubSyncError(f"GitHub unreachable: {err}") from err
        return True
