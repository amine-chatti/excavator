from __future__ import annotations

from fastapi.testclient import TestClient

from excavator.api.main import create_app


def test_cors_allows_get_and_explain_post_only_from_local_frontends() -> None:
    allowed_origins = ("http://localhost:5173", "http://127.0.0.1:5173")
    with TestClient(create_app()) as client:
        for origin in allowed_origins:
            response = client.get("/health", headers={"Origin": origin})
            assert response.status_code == 200
            assert response.headers["access-control-allow-origin"] == origin
            assert "access-control-allow-credentials" not in response.headers

        disallowed = client.get(
            "/health",
            headers={"Origin": "http://localhost:5174"},
        )
        assert disallowed.status_code == 200
        assert "access-control-allow-origin" not in disallowed.headers

        get_preflight = client.options(
            "/health",
            headers={
                "Origin": allowed_origins[0],
                "Access-Control-Request-Method": "GET",
            },
        )
        assert get_preflight.status_code == 200
        assert get_preflight.headers["access-control-allow-methods"] == "GET, POST"

        post_preflight = client.options(
            "/symbols/1/explain",
            headers={
                "Origin": allowed_origins[0],
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        assert post_preflight.status_code == 200
        assert post_preflight.headers["access-control-allow-origin"] == allowed_origins[0]
        assert post_preflight.headers["access-control-allow-methods"] == "GET, POST"
        allowed_headers = {
            header.strip().lower()
            for header in post_preflight.headers["access-control-allow-headers"].split(",")
        }
        assert "content-type" in allowed_headers

        disallowed_preflight = client.options(
            "/symbols/1/explain",
            headers={
                "Origin": "http://localhost:5174",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        assert disallowed_preflight.status_code == 400
        assert "access-control-allow-origin" not in disallowed_preflight.headers

        for method in ("PUT", "DELETE"):
            denied_preflight = client.options(
                "/symbols/1/explain",
                headers={
                    "Origin": allowed_origins[0],
                    "Access-Control-Request-Method": method,
                },
            )
            assert denied_preflight.status_code == 400
