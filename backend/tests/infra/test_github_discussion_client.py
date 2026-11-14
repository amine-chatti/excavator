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


def _comment() -> dict[str, object]:
    return {
        "id": 42,
        "pull_request_review_id": 14,
        "in_reply_to_id": None,
        "path": "src/a.py",
        "diff_hunk": "@@ -1 +1 @@",
        "commit_id": "a" * 40,
        "original_commit_id": "b" * 40,
        "line": 1,
        "start_line": None,
        "original_line": 1,
        "original_start_line": None,
        "side": "RIGHT",
        "start_side": None,
        "subject_type": "line",
        "body": "comment",
        "user": {"login": "octocat"},
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-02T00:00:00Z",
        "html_url": "https://github.com/owner/repo/pull/7#comment-42",
    }


def _issue() -> dict[str, object]:
    return {
        "number": 7,
        "title": "Issue",
        "body": None,
        "state": "closed",
        "user": {"login": "octocat"},
        "created_at": "2026-01-01T00:00:00Z",
        "closed_at": "2026-01-02T00:00:00Z",
        "html_url": "https://github.com/owner/repo/issues/7",
    }


def test_review_comments_parse_and_paginate_with_transport() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json=[_comment()],
                headers={"Link": '<https://api.github.test/page/2>; rel="next", <x>; rel="last"'},
            )
        return httpx.Response(200, json=[{**_comment(), "id": 43}])

    client = HttpGitHubClient(
        "token-value",
        "https://api.github.test",
        transport=httpx.MockTransport(handler),
    )
    comments = client.list_review_comments("owner", "repo", 7)
    assert [item.github_id for item in comments] == [42, 43]
    assert comments[0].created_at == datetime(2026, 1, 1, tzinfo=UTC)
    assert requests[0].headers["Authorization"] == "Bearer token-value"
    assert requests[0].url.path.endswith("/pulls/7/comments")
    assert requests[1].url == "https://api.github.test/page/2"
    assert GITHUB_API_TIMEOUT_SECONDS == 30


def test_review_comments_raise_after_maximum_pages() -> None:
    count = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal count
        count += 1
        return httpx.Response(
            200,
            json=[],
            headers={"Link": f'<https://api.github.test/page/{count + 1}>; rel="next"'},
        )

    with pytest.raises(GitHubClientError, match="too many pages"):
        HttpGitHubClient(transport=httpx.MockTransport(handler)).list_review_comments(
            "owner", "repo", 7
        )


def test_review_comments_reject_non_list_json_and_invalid_records() -> None:
    for payload in ({"not": "a list"}, [None]):

        def handler(_request: httpx.Request, result: object = payload) -> httpx.Response:
            return httpx.Response(200, json=result)

        transport = httpx.MockTransport(handler)
        with pytest.raises(GitHubClientError, match="malformed response"):
            HttpGitHubClient(transport=transport).list_review_comments("owner", "repo", 7)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.pop("id"),
        lambda value: value.update({"id": "bad"}),
        lambda value: value.update({"path": 3}),
        lambda value: value.update({"line": "bad"}),
        lambda value: value.update({"created_at": "bad-date"}),
        lambda value: value.update({"user": {"login": 3}}),
    ],
)
def test_review_comment_malformed_fields_are_generic(
    mutate: Callable[[dict[str, object]], object],
) -> None:
    payload = _comment()
    mutate(payload)
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, json=[payload]))
    with pytest.raises(GitHubClientError, match="malformed response"):
        HttpGitHubClient("never-show-this", transport=transport).list_review_comments(
            "owner", "repo", 7
        )


def test_issue_parsing_404_and_pull_request_detection() -> None:
    payload = _issue()
    client = HttpGitHubClient(
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=payload))
    )
    issue = client.get_issue("owner", "repo", 7)
    assert issue is not None
    assert issue.number == 7
    assert issue.state == "closed"
    assert issue.closed_at == datetime(2026, 1, 2, tzinfo=UTC)

    missing = HttpGitHubClient(transport=httpx.MockTransport(lambda _request: httpx.Response(404)))
    assert missing.get_issue("owner", "repo", 7) is None

    pull_request = HttpGitHubClient(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(200, json={**payload, "pull_request": {}})
        )
    )
    assert pull_request.get_issue("owner", "repo", 7) is None


@pytest.mark.parametrize("status", [403, 429])
def test_discussion_client_maps_rate_limits_without_token(status: int) -> None:
    token = "do-not-disclose"
    transport = httpx.MockTransport(lambda _request: httpx.Response(status))
    with pytest.raises(GitHubRateLimitError) as error:
        HttpGitHubClient(token, transport=transport).get_issue("owner", "repo", 7)
    assert token not in str(error.value)


def test_issue_malformed_json_and_fields_are_generic() -> None:
    responses = [
        httpx.Response(200, content=b"not-json"),
        httpx.Response(200, json={"number": 7}),
        httpx.Response(200, json=[]),
    ]
    client = HttpGitHubClient(
        "do-not-disclose",
        transport=httpx.MockTransport(lambda _request: responses.pop(0)),
    )
    for _ in range(3):
        with pytest.raises(GitHubClientError, match="malformed response") as error:
            client.get_issue("owner", "repo", 7)
        assert "do-not-disclose" not in str(error.value)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.update({"number": True}),
        lambda value: value.update({"title": 4}),
        lambda value: value.update({"body": 4}),
        lambda value: value.update({"user": 4}),
        lambda value: value.update({"user": {"login": 4}}),
        lambda value: value.update({"closed_at": 4}),
    ],
)
def test_issue_wrongly_typed_fields_are_generic(
    mutate: Callable[[dict[str, object]], object],
) -> None:
    payload = _issue()
    mutate(payload)
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, json=payload))
    with pytest.raises(GitHubClientError, match="malformed response"):
        HttpGitHubClient(transport=transport).get_issue("owner", "repo", 7)


def test_discussion_client_timeout_maps_to_generic_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("sensitive")

    with pytest.raises(GitHubClientError, match="timed out"):
        HttpGitHubClient(transport=httpx.MockTransport(handler)).get_issue("owner", "repo", 7)


def test_discussion_client_maps_request_and_http_errors() -> None:
    def request_error(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sensitive")

    with pytest.raises(GitHubClientError, match="request failed"):
        HttpGitHubClient(transport=httpx.MockTransport(request_error)).get_issue("owner", "repo", 7)
    with pytest.raises(GitHubClientError, match="status 500"):
        HttpGitHubClient(
            transport=httpx.MockTransport(lambda _request: httpx.Response(500))
        ).get_issue("owner", "repo", 7)


def test_invalid_discussion_numbers_and_zero_page_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    client = HttpGitHubClient()
    with pytest.raises(ValueError):
        client.get_issue("owner", "repo", 0)
    with pytest.raises(ValueError):
        client.list_review_comments("owner", "repo", 0)
    monkeypatch.setattr("excavator.infra.github_client.GITHUB_MAX_PAGES", 0)
    with pytest.raises(GitHubClientError, match="too many pages"):
        HttpGitHubClient().list_review_comments("owner", "repo", 7)


def test_review_comment_bad_optional_fields_and_user_are_rejected() -> None:
    mutations: tuple[Callable[[dict[str, object]], object], ...] = (
        lambda value: value.update({"side": 3}),
        lambda value: value.update({"user": 3}),
    )
    for mutate in mutations:
        payload = _comment()
        mutate(payload)

        def handler(_request: httpx.Request, result: dict[str, object] = payload) -> httpx.Response:
            return httpx.Response(200, json=[result])

        transport = httpx.MockTransport(handler)
        with pytest.raises(GitHubClientError, match="malformed response"):
            HttpGitHubClient(transport=transport).list_review_comments("owner", "repo", 7)


def test_link_header_without_valid_next_target_is_ignored() -> None:
    from excavator.infra.github_client import _next_link

    assert _next_link(None) is None
    assert _next_link("<bad>; rel=next") is None
