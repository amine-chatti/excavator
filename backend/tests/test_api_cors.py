from __future__ import annotations

from fastapi.testclient import TestClient

from excavator.api.main import create_app


def test_cors_allows_only_the_two_local_frontend_origins_for_get() -> None:
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
        assert get_preflight.headers["access-control-allow-methods"] == "GET"

        post_preflight = client.options(
            "/health",
            headers={
                "Origin": allowed_origins[0],
                "Access-Control-Request-Method": "POST",
            },
        )
        assert post_preflight.status_code == 400
