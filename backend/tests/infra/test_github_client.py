from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import httpx
import pytest

from excavator.infra.github_client import (
    GITHUB_API_TIMEOUT_SECONDS,
    GitHubClientError,
    GitHubRateLimitError,
    HttpGitHubClient,
)


def _payload() -> dict[str, object]:
    return {
        "number": 7,
        "title": "Improve parser",
        "body": "Details",
        "state": "open",
        "user": {"login": "octocat"},
        "created_at": "2026-01-02T03:04:05Z",
        "merged_at": "2026-01-03T03:04:05Z",
        "html_url": "https://github.com/owner/repo/pull/7",
        "base": {"ref": "main"},
    }


def test_list_pull_requests_parses_response_and_uses_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, object] = {}

    def fake_get(url: str, **kwargs: object) -> httpx.Response:
        calls["url"] = url
        calls.update(kwargs)
        return httpx.Response(200, json=[_payload()])

    monkeypatch.setattr(httpx, "get", fake_get)
    result = HttpGitHubClient("secret-token").list_pull_requests_for_commit(
        "owner",
        "repo",
        "a" * 40,
    )

    assert result[0].number == 7
    assert result[0].base_ref == "main"
    assert result[0].merged is True
    assert result[0].merge_method == "unknown"
    assert result[0].created_at == datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    assert calls["url"] == "https://api.github.com/repos/owner/repo/commits/" + "a" * 40 + "/pulls"
    assert calls["timeout"] == GITHUB_API_TIMEOUT_SECONDS
    assert calls["headers"] == {
        "Accept": "application/vnd.github+json",
        "Authorization": "Bearer secret-token",
    }


def test_client_supports_custom_https_base_and_nullable_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _payload()
    payload.pop("body")
    payload.pop("user")
    payload["merged_at"] = None

    monkeypatch.setattr(
        httpx,
        "get",
        lambda *args, **kwargs: httpx.Response(200, json=[payload]),
    )
    result = HttpGitHubClient(base_url="https://api.github.test").list_pull_requests_for_commit(
        "owner",
        "repo",
        "b" * 40,
    )

    assert result[0].body is None
    assert result[0].author_login is None
    assert result[0].merged_at is None
    assert result[0].merged is False


@pytest.mark.parametrize(
    "base",
    [
        None,
        {},
        {"ref": ""},
        {"ref": 1},
    ],
)
def test_malformed_base_fields_raise_generic_error(
    monkeypatch: pytest.MonkeyPatch,
    base: object,
) -> None:
    value = _payload()
    if base is None:
        value.pop("base")
    else:
        value["base"] = base
    monkeypatch.setattr(
        httpx,
        "get",
        lambda *args, **kwargs: httpx.Response(200, json=[value]),
    )

    with pytest.raises(GitHubClientError, match="malformed response"):
        HttpGitHubClient().list_pull_requests_for_commit("owner", "repo", "c" * 40)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.update({"body": 1}),
        lambda value: value.update({"user": 1}),
        lambda value: value.update({"user": {"login": 1}}),
        lambda value: value.update({"merged_at": 1}),
        lambda value: value.update({"created_at": 1}),
        lambda value: value.update({"created_at": "not-a-date"}),
    ],
)
def test_malformed_pull_request_fields_raise_generic_error(
    monkeypatch: pytest.MonkeyPatch,
    mutate: Callable[[dict[str, object]], None],
) -> None:
    value = _payload()
    mutate(value)
    monkeypatch.setattr(
        httpx,
        "get",
        lambda *args, **kwargs: httpx.Response(200, json=[value]),
    )

    with pytest.raises(GitHubClientError, match="malformed response"):
        HttpGitHubClient().list_pull_requests_for_commit("owner", "repo", "c" * 40)


def test_non_list_response_is_malformed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: httpx.Response(200, json={}))

    with pytest.raises(GitHubClientError, match="malformed response"):
        HttpGitHubClient().list_pull_requests_for_commit("owner", "repo", "c" * 40)


def test_non_object_pull_request_is_malformed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: httpx.Response(200, json=[None]))

    with pytest.raises(GitHubClientError, match="malformed response"):
        HttpGitHubClient().list_pull_requests_for_commit("owner", "repo", "c" * 40)


@pytest.mark.parametrize("status", [403, 429])
def test_rate_limit_status_is_distinguished(
    monkeypatch: pytest.MonkeyPatch,
    status: int,
) -> None:
    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: httpx.Response(status))

    with pytest.raises(GitHubRateLimitError, match=str(status)):
        HttpGitHubClient().list_pull_requests_for_commit("owner", "repo", "d" * 40)


def test_http_error_does_not_expose_token(monkeypatch: pytest.MonkeyPatch) -> None:
    token = "super-secret-token"
    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: httpx.Response(404))

    with pytest.raises(GitHubClientError) as error:
        HttpGitHubClient(token).list_pull_requests_for_commit("owner", "repo", "e" * 40)

    assert token not in str(error.value)


def test_timeout_and_request_error_are_generic(monkeypatch: pytest.MonkeyPatch) -> None:
    def timeout(*args: object, **kwargs: object) -> httpx.Response:
        raise httpx.TimeoutException("secret")

    monkeypatch.setattr(httpx, "get", timeout)
    with pytest.raises(GitHubClientError, match="timed out"):
        HttpGitHubClient().list_pull_requests_for_commit("owner", "repo", "f" * 40)

    def request_error(*args: object, **kwargs: object) -> httpx.Response:
        raise httpx.RequestError("secret")

    monkeypatch.setattr(httpx, "get", request_error)
    with pytest.raises(GitHubClientError, match="request failed"):
        HttpGitHubClient().list_pull_requests_for_commit("owner", "repo", "0" * 40)


@pytest.mark.parametrize(
    ("owner", "name", "sha"),
    [
        ("bad/name", "repo", "a" * 40),
        ("owner", "..", "a" * 40),
        ("owner", "repo", "A" * 40),
        ("owner", "repo", "a" * 39),
    ],
)
def test_client_validates_identifiers_and_sha(
    owner: str,
    name: str,
    sha: str,
) -> None:
    with pytest.raises(ValueError):
        HttpGitHubClient().list_pull_requests_for_commit(owner, name, sha)


def test_client_rejects_non_https_base() -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        HttpGitHubClient(base_url="http://localhost")
