"""Unit tests for REST API server module.

This module tests the Flask-based REST API endpoints including authentication,
request handling, error cases, and response formatting.

Key Testing Patterns:
    - Use Flask test client for endpoint testing
    - Mock SystemInfoCollector to avoid real system calls
    - Mock run_predefined_command to avoid executing commands
    - Test authentication with Bearer tokens and query parameters
    - Verify correct HTTP status codes and JSON responses

Example Run:
    pytest tests/unit/modules/test_api.py -v
"""

import json
from unittest.mock import patch

import pytest

# Import Flask app and test client after patching
from modules.api import app

# Test token used across all API tests
TEST_API_TOKEN = "test_token_12345"


@pytest.fixture(autouse=True)
def mock_api_auth_token():
    """Patch API_AUTH_TOKEN to use test token for all API tests.

    This fixture patches the API_AUTH_TOKEN constant in both the config
    and api modules to ensure consistent test authentication.
    """
    with patch("modules.core.config.API_AUTH_TOKEN", TEST_API_TOKEN):
        with patch("modules.api.API_AUTH_TOKEN", TEST_API_TOKEN):
            yield TEST_API_TOKEN


@pytest.fixture
def client():
    """Create Flask test client for API testing.

    This fixture provides a test client that can make requests to the API
    without starting an actual server.

    Example:
        def test_endpoint(client):
            response = client.get('/status')
            assert response.status_code == 200
    """
    app.config["TESTING"] = True
    with app.test_client() as test_client:
        yield test_client


@pytest.fixture
def mock_system_collector():
    """Mock SystemInfoCollector to return predictable data."""
    with patch("modules.api.SystemInfoCollector") as mock:
        instance = mock.return_value
        instance.collect_all.return_value = {
            "hostname": "test-host",
            "cpu_usage": 50.0,
            "memory_usage": 60.0,
            "disk_usage": 75.0,
        }
        yield instance


@pytest.fixture
def mock_command_runner():
    """Mock run_predefined_command function."""
    with patch("modules.api.run_predefined_command") as mock:
        mock.return_value = {"success": True, "output": "Command executed"}
        yield mock


class TestAPIAuthentication:
    """Test suite for API authentication."""

    def test_status_requires_auth(self, client):
        """Test that /status endpoint requires authentication."""
        response = client.get("/status")
        assert response.status_code == 401
        data = json.loads(response.data)
        assert "error" in data
        assert data["error"] == "Unauthorized"

    def test_status_with_bearer_token(self, client, mock_system_collector):
        """Test /status endpoint with valid Bearer token authentication."""
        # Use the test token from config (modules/api.py imports API_AUTH_TOKEN)
        headers = {"Authorization": "Bearer test_token_12345"}
        response = client.get("/status", headers=headers)

        # Should succeed with mocked collector
        assert response.status_code == 200

    def test_status_with_query_param_auth(self, client, mock_system_collector):
        """Test /status endpoint with query parameter authentication."""
        response = client.get("/status?auth_token=test_token_12345")
        assert response.status_code == 200

    def test_status_with_invalid_token(self, client):
        """Test /status endpoint with invalid authentication token."""
        headers = {"Authorization": "Bearer invalid_token"}
        response = client.get("/status", headers=headers)
        assert response.status_code == 401

    def test_status_with_malformed_bearer(self, client):
        """Test /status endpoint with malformed Bearer header."""
        # Missing 'Bearer ' prefix
        headers = {"Authorization": "test_token_12345"}
        response = client.get("/status", headers=headers)
        assert response.status_code == 401

    def test_run_requires_auth(self, client):
        """Test that /run endpoint requires authentication."""
        response = client.post(
            "/run", json={"command": "test"}, content_type="application/json"
        )
        assert response.status_code == 401

    def test_auth_timing_attack_resistance(self, client):
        """Test that authentication uses constant-time comparison.

        This test verifies that the API uses secrets.compare_digest()
        by ensuring it doesn't leak information through timing.
        While we can't easily test timing directly, we verify the behavior
        with different invalid tokens.
        """
        # Both should fail with same response time (approximately)
        headers1 = {"Authorization": "Bearer wrong"}
        headers2 = {"Authorization": "Bearer test_token_12344"}  # Close to valid

        response1 = client.get("/status", headers=headers1)
        response2 = client.get("/status", headers=headers2)

        # Both should fail with 401
        assert response1.status_code == 401
        assert response2.status_code == 401


class TestStatusEndpoint:
    """Test suite for /status endpoint."""

    def test_status_success(self, client, mock_system_collector):
        """Test successful /status request."""
        headers = {"Authorization": "Bearer test_token_12345"}
        response = client.get("/status", headers=headers)

        assert response.status_code == 200
        data = json.loads(response.data)

        # Verify expected data structure
        assert "hostname" in data
        assert "cpu_usage" in data
        assert "memory_usage" in data
        assert "disk_usage" in data

    def test_status_returns_json(self, client, mock_system_collector):
        """Test that /status returns valid JSON."""
        headers = {"Authorization": "Bearer test_token_12345"}
        response = client.get("/status", headers=headers)

        assert response.content_type == "application/json"
        # Should not raise on parse
        data = json.loads(response.data)
        assert isinstance(data, dict)

    def test_status_collector_error(self, client):
        """Test /status endpoint when SystemInfoCollector raises exception."""
        with patch("modules.api.SystemInfoCollector") as mock:
            mock.return_value.collect_all.side_effect = Exception("Collector failed")

            headers = {"Authorization": "Bearer test_token_12345"}
            response = client.get("/status", headers=headers)

            assert response.status_code == 500
            data = json.loads(response.data)
            assert "error" in data
            assert data["error"] == "Internal server error"

    def test_status_get_method_only(self, client, mock_system_collector):
        """Test that /status only accepts GET method."""
        headers = {"Authorization": "Bearer test_token_12345"}

        # GET should work
        response = client.get("/status", headers=headers)
        assert response.status_code == 200

        # POST should fail
        response = client.post("/status", headers=headers)
        assert response.status_code == 405  # Method Not Allowed


class TestRunEndpoint:
    """Test suite for /run endpoint."""

    def test_run_success(self, client, mock_command_runner):
        """Test successful command execution via /run endpoint."""
        headers = {"Authorization": "Bearer test_token_12345"}
        response = client.post("/run", headers=headers, json={"command": "test_command"})

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["success"] is True
        assert "output" in data

        # Verify the command was called
        mock_command_runner.assert_called_once_with("test_command")

    def test_run_missing_command_key(self, client, mock_command_runner):
        """Test /run endpoint with missing command key."""
        headers = {"Authorization": "Bearer test_token_12345"}
        response = client.post("/run", headers=headers, json={})

        assert response.status_code == 400
        data = json.loads(response.data)
        assert data["success"] is False
        assert "No command provided" in data["output"]

    def test_run_null_json(self, client, mock_command_runner):
        """Test /run endpoint with null JSON body."""
        headers = {
            "Authorization": "Bearer test_token_12345",
            "Content-Type": "application/json",
        }
        response = client.post("/run", headers=headers, data="{}")

        assert response.status_code == 400
        data = json.loads(response.data)
        assert data["success"] is False

    def test_run_command_failure(self, client):
        """Test /run endpoint when command execution fails."""
        with patch("modules.api.run_predefined_command") as mock:
            mock.return_value = {"success": False, "output": "Command not found"}

            headers = {"Authorization": "Bearer test_token_12345"}
            response = client.post(
                "/run", headers=headers, json={"command": "invalid_cmd"}
            )

            assert response.status_code == 400
            data = json.loads(response.data)
            assert data["success"] is False
            assert "Command not found" in data["output"]

    def test_run_internal_error(self, client):
        """Test /run endpoint when an exception occurs."""
        with patch("modules.api.run_predefined_command") as mock:
            mock.side_effect = Exception("Internal error")

            headers = {"Authorization": "Bearer test_token_12345"}
            response = client.post("/run", headers=headers, json={"command": "test"})

            assert response.status_code == 500
            data = json.loads(response.data)
            assert data["success"] is False
            assert data["output"] == "Internal server error"

    def test_run_post_method_only(self, client):
        """Test that /run only accepts POST method."""
        headers = {"Authorization": "Bearer test_token_12345"}

        # GET should fail
        response = client.get("/run", headers=headers)
        assert response.status_code == 405  # Method Not Allowed

        # POST should work (with mocked command)
        with patch("modules.api.run_predefined_command") as mock:
            mock.return_value = {"success": True, "output": "OK"}
            response = client.post("/run", headers=headers, json={"command": "test"})
            assert response.status_code == 200

    def test_run_invalid_json(self, client):
        """Test /run endpoint with malformed JSON."""
        headers = {
            "Authorization": "Bearer test_token_12345",
            "Content-Type": "application/json",
        }
        # Send invalid JSON
        response = client.post("/run", headers=headers, data="{invalid json")

        # Flask should handle this and return 400 or similar
        assert response.status_code in [400, 500]


class TestSecurityHeaders:
    """Test suite for security headers."""

    def test_security_headers_present(self, client, mock_system_collector):
        """Test that security headers are added to responses."""
        headers = {"Authorization": "Bearer test_token_12345"}
        response = client.get("/status", headers=headers)

        # Verify security headers
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"
        assert response.headers.get("X-XSS-Protection") == "1; mode=block"

    def test_security_headers_on_error(self, client):
        """Test that security headers are present even on error responses."""
        # Unauthenticated request
        response = client.get("/status")

        assert response.status_code == 401
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"


class TestEndpointNotFound:
    """Test suite for non-existent endpoints."""

    def test_404_for_unknown_endpoint(self, client):
        """Test that unknown endpoints return 404."""
        headers = {"Authorization": "Bearer test_token_12345"}
        response = client.get("/unknown", headers=headers)
        assert response.status_code == 404

    def test_root_endpoint(self, client):
        """Test that root endpoint is not defined."""
        headers = {"Authorization": "Bearer test_token_12345"}
        response = client.get("/", headers=headers)
        # Should return 404 since no root route is defined
        assert response.status_code == 404


class TestAuthenticationEdgeCases:
    """Test edge cases in authentication."""

    def test_empty_auth_header(self, client):
        """Test with empty Authorization header."""
        headers = {"Authorization": ""}
        response = client.get("/status", headers=headers)
        assert response.status_code == 401

    def test_bearer_with_spaces(self, client):
        """Test Bearer token with extra spaces."""
        # Extra space after Bearer
        headers = {"Authorization": "Bearer  test_token_12345"}
        response = client.get("/status", headers=headers)
        # Should fail due to extra space (not the exact token)
        assert response.status_code == 401

    def test_case_sensitive_bearer(self, client, mock_system_collector):
        """Test that 'Bearer' prefix is case-sensitive."""
        # Lowercase 'bearer'
        headers = {"Authorization": "bearer test_token_12345"}
        response = client.get("/status", headers=headers)
        # Should fail - implementation expects 'Bearer' with capital B
        assert response.status_code == 401

    def test_query_param_and_header_precedence(self, client, mock_system_collector):
        """Test authentication when both header and query param are present.

        The implementation checks header first, so header takes precedence.
        """
        headers = {"Authorization": "Bearer test_token_12345"}
        # Also provide query param (which would fail if used)
        response = client.get("/status?auth_token=wrong_token", headers=headers)

        # Should succeed because header is checked first and is valid
        assert response.status_code == 200
