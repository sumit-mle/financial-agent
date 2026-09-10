"""
Tests for the admin API (`/api/v1/admin/*`) plus the app-level root/health routes.

Auth model under test: privileged admin routes are guarded by ``require_admin``,
which compares an ``Authorization: Bearer <token>`` header against
``settings.admin_token`` using a constant-time comparison, in *every*
environment. ``/api/v1/admin/health`` is intentionally public so load balancers
and container healthchecks can probe it.
"""
from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient


@pytest.mark.api
class TestAdminHealth:
    """The public health endpoint."""

    async def test_health_reports_every_service(self, test_client: AsyncClient):
        resp = await test_client.get("/api/v1/admin/health")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("ok", "degraded")
        assert "version" in data
        # Each dependency is reported with a coarse, non-leaky status string.
        for service in ("qdrant", "redis", "postgres", "salesforce"):
            assert service in data["services"]
            assert data["services"][service] in ("ok", "error", "not_configured")

    async def test_health_is_degraded_when_a_dependency_fails(
        self, test_client: AsyncClient
    ):
        # Patch where the name is looked up (inside the handler), not at source.
        with patch("qdrant_client.QdrantClient") as mock_qdrant:
            mock_qdrant.return_value.get_collections.side_effect = Exception(
                "Qdrant connection failed"
            )
            resp = await test_client.get("/api/v1/admin/health")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "degraded"
        assert data["services"]["qdrant"] == "error"

    async def test_health_does_not_leak_exception_detail(
        self, test_client: AsyncClient
    ):
        """Failure statuses must be coarse — no driver/DSN internals."""
        secret = "super-secret-dsn-detail"
        with patch("qdrant_client.QdrantClient") as mock_qdrant:
            mock_qdrant.return_value.get_collections.side_effect = Exception(secret)
            resp = await test_client.get("/api/v1/admin/health")

        assert secret not in resp.text

    async def test_health_needs_no_auth(self, test_client: AsyncClient):
        """Probes must not require credentials."""
        resp = await test_client.get("/api/v1/admin/health")
        assert resp.status_code == 200


@pytest.mark.api
class TestAdminAuth:
    """Every privileged admin route must reject missing/incorrect credentials."""

    PROTECTED = (
        ("GET", "/api/v1/admin/status", None),
        ("POST", "/api/v1/admin/ingest", {"source": "cfpb", "sample_mode": True}),
    )

    @pytest.mark.parametrize("method,path,payload", PROTECTED)
    async def test_rejects_missing_token(
        self, test_client: AsyncClient, method, path, payload
    ):
        resp = await test_client.request(method, path, json=payload)
        assert resp.status_code in (401, 403)

    @pytest.mark.parametrize("method,path,payload", PROTECTED)
    async def test_rejects_wrong_token(
        self, test_client: AsyncClient, method, path, payload
    ):
        headers = {"Authorization": "Bearer wrong-token"}
        resp = await test_client.request(method, path, json=payload, headers=headers)
        assert resp.status_code == 401

    @pytest.mark.parametrize("method,path,payload", PROTECTED)
    async def test_rejects_wrong_scheme(
        self, test_client: AsyncClient, method, path, payload
    ):
        """A legacy X-API-Key header alone must not authenticate."""
        headers = {"X-API-Key": "some-key"}
        resp = await test_client.request(method, path, json=payload, headers=headers)
        assert resp.status_code in (401, 403)


@pytest.mark.api
class TestVectorStoreStatus:
    async def test_status_returns_collection_counts(
        self, test_client: AsyncClient, admin_headers
    ):
        with patch("app.api.routes.admin.VectorStoreWriter") as mock_writer:
            instance = MagicMock()
            # complaints, policies, faq — in call order
            instance.collection_count.side_effect = [43532, 10, 5]
            mock_writer.return_value = instance

            resp = await test_client.get("/api/v1/admin/status", headers=admin_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["complaints"] == 43532
        assert data["policies"] == 10
        assert data["faq"] == 5
        assert data["total"] == 43547


@pytest.mark.api
class TestTriggerIngestion:
    async def test_ingest_starts_background_job(
        self, test_client: AsyncClient, admin_headers
    ):
        # The route schedules a BackgroundTask that really executes under
        # ASGITransport, so the pipeline MUST be patched or the test would kick
        # off a live CFPB download.
        with patch("app.api.routes.admin.IngestionPipeline") as mock_pipeline:
            instance = MagicMock()
            instance.run_cfpb.return_value = {"documents": 100, "vectors": 500}
            mock_pipeline.return_value = instance

            resp = await test_client.post(
                "/api/v1/admin/ingest",
                json={"source": "cfpb", "sample_mode": True},
                headers=admin_headers,
            )

            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "started"
            assert "cfpb" in data["message"].lower()
            # Background task ran and honoured sample_mode.
            instance.run_cfpb.assert_called_once_with(sample_mode=True)

    async def test_ingest_rejects_unknown_source(
        self, test_client: AsyncClient, admin_headers
    ):
        resp = await test_client.post(
            "/api/v1/admin/ingest",
            json={"source": "not_a_source", "sample_mode": True},
            headers=admin_headers,
        )
        assert resp.status_code == 422

    async def test_ingest_is_rejected_while_one_is_running(
        self, test_client: AsyncClient, admin_headers
    ):
        """The module-level guard must refuse a concurrent ingestion run."""
        with patch("app.api.routes.admin._ingest_running", True):
            resp = await test_client.post(
                "/api/v1/admin/ingest",
                json={"source": "cfpb", "sample_mode": True},
                headers=admin_headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "error"
        assert "already in progress" in data["message"].lower()


@pytest.mark.api
class TestAppLevelRoutes:
    async def test_root_lists_navigation(self, test_client: AsyncClient):
        resp = await test_client.get("/")

        assert resp.status_code == 200
        data = resp.json()
        for key in ("name", "version", "docs", "health", "chat"):
            assert key in data
        assert data["docs"] == "/docs"
        assert data["health"] == "/health"

    async def test_liveness_probe(self, test_client: AsyncClient):
        resp = await test_client.get("/health")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data

    async def test_metrics_endpoint(self, test_client: AsyncClient):
        resp = await test_client.get("/metrics")

        # Instrumentator is wired during lifespan; it may be absent when the app
        # is exercised without a lifespan run.
        assert resp.status_code in (200, 404)
        if resp.status_code == 200:
            assert "# HELP" in resp.text or "# TYPE" in resp.text
