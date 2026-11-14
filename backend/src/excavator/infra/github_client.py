from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

import httpx

from excavator.config import Settings

GITHUB_API_TIMEOUT_SECONDS = 30


class GitHubClientError(Exception):
    """Raised when a GitHub API response cannot be used."""


class GitHubRateLimitError(GitHubClientError):
    """Raised when GitHub reports an API rate limit."""


@dataclass(frozen=True, slots=True)
class PullRequestData:
    number: int
    title: str
    body: str | None
    state: str
    author_login: str | None
    created_at: datetime
    merged_at: datetime | None
    url: str
    base_ref: str
    merged: bool
    merge_method: str


class GitHubClient(Protocol):
    def list_pull_requests_for_commit(
        self,
        owner: str,
        name: str,
        sha: str,
    ) -> tuple[PullRequestData, ...]: ...


class HttpGitHubClient:
    def __init__(
        self,
        token: str | None = None,
        base_url: str = "https://api.github.com",
    ) -> None:
        if not base_url.startswith("https://"):
            raise ValueError("GitHub base URL must use HTTPS")
        self._token = token
        self._base_url = base_url.rstrip("/")

    @classmethod
    def from_settings(cls, settings: Settings) -> HttpGitHubClient:
        token = settings.GITHUB_TOKEN.get_secret_value() if settings.GITHUB_TOKEN else None
        return cls(token=token)

    def list_pull_requests_for_commit(
        self,
        owner: str,
        name: str,
        sha: str,
    ) -> tuple[PullRequestData, ...]:
        _validate_identifier(owner, "owner")
        _validate_identifier(name, "name")
        _validate_sha(sha)
        headers = {"Accept": "application/vnd.github+json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        try:
            response = httpx.get(
                f"{self._base_url}/repos/{owner}/{name}/commits/{sha}/pulls",
                headers=headers,
                timeout=GITHUB_API_TIMEOUT_SECONDS,
            )
        except httpx.TimeoutException as exc:
            raise GitHubClientError("GitHub API request timed out") from exc
        except httpx.RequestError as exc:
            raise GitHubClientError("GitHub API request failed") from exc
        if response.status_code in {403, 429}:
            raise GitHubRateLimitError(f"GitHub API rate limit response: {response.status_code}")
        if response.status_code >= 400:
            raise GitHubClientError(f"GitHub API request failed with status {response.status_code}")
        try:
            payload = response.json()
            if not isinstance(payload, list):
                raise ValueError
            return tuple(_parse_pull_request(item) for item in payload)
        except (TypeError, ValueError, KeyError, AttributeError, IndexError) as exc:
            raise GitHubClientError("GitHub API returned a malformed response") from exc


def _validate_identifier(value: str, label: str) -> None:
    if (
        not value
        or value in {".", ".."}
        or any(
            not (character.isascii() and (character.isalnum() or character in "._-"))
            for character in value
        )
    ):
        raise ValueError(f"{label} is invalid")


def _validate_sha(value: str) -> None:
    if len(value) != 40 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError("sha must be a 40-character lowercase hexadecimal SHA-1")


def _parse_pull_request(value: object) -> PullRequestData:
    if not isinstance(value, dict):
        raise ValueError
    number = value["number"]
    title = value["title"]
    state = value["state"]
    created_at = _parse_datetime(value["created_at"])
    url = value["html_url"]
    base = value["base"]
    if (
        isinstance(number, bool)
        or not isinstance(number, int)
        or not isinstance(title, str)
        or not isinstance(state, str)
        or not isinstance(url, str)
        or not url
        or not isinstance(base, dict)
        or not isinstance(base.get("ref"), str)
        or not base["ref"]
    ):
        raise ValueError
    body = value.get("body")
    if body is not None and not isinstance(body, str):
        raise ValueError
    user = value.get("user")
    author_login: str | None = None
    if user is not None:
        if not isinstance(user, dict):
            raise ValueError
        author_login = user.get("login")
        if author_login is not None and not isinstance(author_login, str):
            raise ValueError
    merged_at_value = value.get("merged_at")
    if merged_at_value is not None and not isinstance(merged_at_value, str):
        raise ValueError
    merged_at = (
        _parse_datetime(merged_at_value)
        if isinstance(merged_at_value, str) and merged_at_value
        else None
    )
    return PullRequestData(
        number=number,
        title=title,
        body=body,
        state=state,
        author_login=author_login,
        created_at=created_at,
        merged_at=merged_at,
        url=url,
        base_ref=base["ref"],
        # This endpoint does not reliably include a merged boolean.
        merged=bool(merged_at_value),
        merge_method="unknown",
    )


def _parse_datetime(value: object) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
