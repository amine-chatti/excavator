from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

import httpx

from excavator.config import Settings

GITHUB_API_TIMEOUT_SECONDS = 30
GITHUB_MAX_PAGES = 5


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


@dataclass(frozen=True, slots=True)
class ReviewCommentData:
    github_id: int
    review_github_id: int | None
    in_reply_to_github_id: int | None
    path: str
    diff_hunk: str
    commit_sha: str
    original_commit_sha: str
    line: int | None
    start_line: int | None
    original_line: int | None
    original_start_line: int | None
    side: str | None
    start_side: str | None
    subject_type: str | None
    body: str
    author_login: str | None
    created_at: datetime
    updated_at: datetime
    url: str


@dataclass(frozen=True, slots=True)
class IssueData:
    number: int
    title: str
    body: str | None
    state: str
    author_login: str | None
    created_at: datetime
    closed_at: datetime | None
    url: str


class GitHubClient(Protocol):
    def list_pull_requests_for_commit(
        self,
        owner: str,
        name: str,
        sha: str,
    ) -> tuple[PullRequestData, ...]: ...


class DiscussionGitHubClient(Protocol):
    def list_review_comments(
        self, owner: str, name: str, pr_number: int
    ) -> tuple[ReviewCommentData, ...]: ...

    def get_issue(self, owner: str, name: str, number: int) -> IssueData | None: ...


class HttpGitHubClient:
    def __init__(
        self,
        token: str | None = None,
        base_url: str = "https://api.github.com",
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not base_url.startswith("https://"):
            raise ValueError("GitHub base URL must use HTTPS")
        self._token = token
        self._base_url = base_url.rstrip("/")
        self._transport = transport

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

    def list_review_comments(
        self, owner: str, name: str, pr_number: int
    ) -> tuple[ReviewCommentData, ...]:
        _validate_identifier(owner, "owner")
        _validate_identifier(name, "name")
        _validate_number(pr_number)
        url = f"{self._base_url}/repos/{owner}/{name}/pulls/{pr_number}/comments"
        results: list[ReviewCommentData] = []
        for page in range(GITHUB_MAX_PAGES):
            response = self._get(url)
            assert response is not None
            try:
                payload = response.json()
                if not isinstance(payload, list):
                    raise ValueError
                results.extend(_parse_review_comment(item) for item in payload)
            except (TypeError, ValueError, KeyError, AttributeError, IndexError) as exc:
                raise GitHubClientError("GitHub API returned a malformed response") from exc
            next_url = _next_link(response.headers.get("Link"))
            if next_url is None:
                return tuple(results)
            if page == GITHUB_MAX_PAGES - 1:
                raise GitHubClientError("GitHub API returned too many pages")
            url = next_url
        raise GitHubClientError("GitHub API returned too many pages")

    def get_issue(self, owner: str, name: str, number: int) -> IssueData | None:
        _validate_identifier(owner, "owner")
        _validate_identifier(name, "name")
        _validate_number(number)
        response = self._get(
            f"{self._base_url}/repos/{owner}/{name}/issues/{number}", allow_404=True
        )
        if response is None:
            return None
        try:
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError
            if "pull_request" in payload:
                return None
            return _parse_issue(payload)
        except (TypeError, ValueError, KeyError, AttributeError, IndexError) as exc:
            raise GitHubClientError("GitHub API returned a malformed response") from exc

    def _get(self, url: str, *, allow_404: bool = False) -> httpx.Response | None:
        headers = {"Accept": "application/vnd.github+json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        try:
            with httpx.Client(
                transport=self._transport,
                timeout=GITHUB_API_TIMEOUT_SECONDS,
            ) as client:
                response = client.get(url, headers=headers)
        except httpx.TimeoutException as exc:
            raise GitHubClientError("GitHub API request timed out") from exc
        except httpx.RequestError as exc:
            raise GitHubClientError("GitHub API request failed") from exc
        if response.status_code in {403, 429}:
            raise GitHubRateLimitError(f"GitHub API rate limit response: {response.status_code}")
        if allow_404 and response.status_code == 404:
            return None
        if response.status_code >= 400:
            raise GitHubClientError(f"GitHub API request failed with status {response.status_code}")
        return response


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


def _validate_number(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("number must be a positive integer")


def _optional_int(value: dict[str, object], key: str) -> int | None:
    item = value.get(key)
    if item is not None and (isinstance(item, bool) or not isinstance(item, int)):
        raise ValueError
    return item


def _optional_str(value: dict[str, object], key: str) -> str | None:
    item = value.get(key)
    if item is not None and not isinstance(item, str):
        raise ValueError
    return item


def _parse_review_comment(value: object) -> ReviewCommentData:
    if not isinstance(value, dict):
        raise ValueError
    github_id = value["id"]
    path, diff_hunk = value["path"], value["diff_hunk"]
    commit_sha, original_commit_sha = value["commit_id"], value["original_commit_id"]
    body, url = value["body"], value["html_url"]
    if (
        isinstance(github_id, bool)
        or not isinstance(github_id, int)
        or not all(
            isinstance(item, str)
            for item in (path, diff_hunk, commit_sha, original_commit_sha, body, url)
        )
        or not url
    ):
        raise ValueError
    user = value.get("user")
    if user is not None and not isinstance(user, dict):
        raise ValueError
    author = None if user is None else user.get("login")
    if author is not None and not isinstance(author, str):
        raise ValueError
    for key in ("line", "start_line", "original_line", "original_start_line"):
        _optional_int(value, key)
    for key in ("side", "start_side", "subject_type"):
        _optional_str(value, key)
    return ReviewCommentData(
        github_id=github_id,
        review_github_id=_optional_int(value, "pull_request_review_id"),
        in_reply_to_github_id=_optional_int(value, "in_reply_to_id"),
        path=path,
        diff_hunk=diff_hunk,
        commit_sha=commit_sha,
        original_commit_sha=original_commit_sha,
        line=_optional_int(value, "line"),
        start_line=_optional_int(value, "start_line"),
        original_line=_optional_int(value, "original_line"),
        original_start_line=_optional_int(value, "original_start_line"),
        side=_optional_str(value, "side"),
        start_side=_optional_str(value, "start_side"),
        subject_type=_optional_str(value, "subject_type"),
        body=body,
        author_login=author,
        created_at=_parse_datetime(value["created_at"]),
        updated_at=_parse_datetime(value["updated_at"]),
        url=url,
    )


def _parse_issue(value: dict[str, object]) -> IssueData:
    number, title, state, url = value["number"], value["title"], value["state"], value["html_url"]
    if (
        isinstance(number, bool)
        or not isinstance(number, int)
        or not isinstance(title, str)
        or not isinstance(state, str)
        or not isinstance(url, str)
        or not url
    ):
        raise ValueError
    body = value.get("body")
    if body is not None and not isinstance(body, str):
        raise ValueError
    user = value.get("user")
    if user is not None and not isinstance(user, dict):
        raise ValueError
    author = None if user is None else user.get("login")
    if author is not None and not isinstance(author, str):
        raise ValueError
    closed = value.get("closed_at")
    if closed is not None and not isinstance(closed, str):
        raise ValueError
    return IssueData(
        number=number,
        title=title,
        body=body,
        state=state,
        author_login=author,
        created_at=_parse_datetime(value["created_at"]),
        closed_at=_parse_datetime(closed) if closed else None,
        url=url,
    )


def _next_link(header: str | None) -> str | None:
    if not header:
        return None
    for part in header.split(","):
        pieces = part.strip().split(";")
        if len(pieces) > 1 and any(piece.strip() == 'rel="next"' for piece in pieces[1:]):
            target = pieces[0].strip()
            if target.startswith("<") and target.endswith(">"):
                return target[1:-1]
    return None
