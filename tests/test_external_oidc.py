"""Tests for authful_mcp_proxy.external_oidc module."""

from unittest.mock import Mock

import pytest

from authful_mcp_proxy.external_oidc import ExternalOIDCAuth, OIDCContext


class TestOIDCContext:
    """Test OIDCContext dataclass and methods."""

    def test_get_redirect_port_with_port(self):
        """Test extracting port from redirect URI."""
        context = OIDCContext(
            issuer_url="https://auth.example.com",
            client_id="test-client",
            client_secret=None,
            scopes=["openid"],
            redirect_uri="http://localhost:8080/callback",
            oidc_config=Mock(),
            storage=Mock(),
        )

        assert context.get_redirect_port() == 8080

    def test_get_redirect_port_default(self):
        """Test default port when not specified."""
        context = OIDCContext(
            issuer_url="https://auth.example.com",
            client_id="test-client",
            client_secret=None,
            scopes=["openid"],
            redirect_uri="http://localhost/callback",
            oidc_config=Mock(),
            storage=Mock(),
        )

        assert context.get_redirect_port() == 80

    def test_is_token_valid_no_tokens(self):
        """Test is_token_valid returns False when no tokens."""
        context = OIDCContext(
            issuer_url="https://auth.example.com",
            client_id="test-client",
            client_secret=None,
            scopes=["openid"],
            redirect_uri="http://localhost:8080/callback",
            oidc_config=Mock(),
            storage=Mock(),
        )

        assert context.is_token_valid() is False

    def test_can_refresh_token_no_tokens(self):
        """Test can_refresh_token returns False when no tokens."""
        context = OIDCContext(
            issuer_url="https://auth.example.com",
            client_id="test-client",
            client_secret=None,
            scopes=["openid"],
            redirect_uri="http://localhost:8080/callback",
            oidc_config=Mock(),
            storage=Mock(),
        )

        assert context.can_refresh_token() is False

    def test_clear_tokens(self):
        """Test clear_tokens sets current_tokens to None."""
        context = OIDCContext(
            issuer_url="https://auth.example.com",
            client_id="test-client",
            client_secret=None,
            scopes=["openid"],
            redirect_uri="http://localhost:8080/callback",
            oidc_config=Mock(),
            storage=Mock(),
        )
        context.current_tokens = Mock()

        context.clear_tokens()

        assert context.current_tokens is None

    def test_get_token_exchange_data_with_secret(self):
        """Test token exchange data includes client secret when provided."""
        context = OIDCContext(
            issuer_url="https://auth.example.com",
            client_id="test-client",
            client_secret="test-secret",
            scopes=["openid"],
            redirect_uri="http://localhost:8080/callback",
            oidc_config=Mock(),
            storage=Mock(),
        )

        pkce = Mock(code_verifier="test-verifier")
        data = context.get_token_exchange_data("auth-code", pkce)

        assert data["grant_type"] == "authorization_code"
        assert data["code"] == "auth-code"
        assert data["client_id"] == "test-client"
        assert data["client_secret"] == "test-secret"
        assert data["code_verifier"] == "test-verifier"
        assert data["redirect_uri"] == "http://localhost:8080/callback"

    def test_get_token_exchange_data_without_secret(self):
        """Test token exchange data excludes client secret when not provided."""
        context = OIDCContext(
            issuer_url="https://auth.example.com",
            client_id="test-client",
            client_secret=None,
            scopes=["openid"],
            redirect_uri="http://localhost:8080/callback",
            oidc_config=Mock(),
            storage=Mock(),
        )

        pkce = Mock(code_verifier="test-verifier")
        data = context.get_token_exchange_data("auth-code", pkce)

        assert "client_secret" not in data

    def test_get_authorization_url(self):
        """Test building authorization URL with PKCE parameters."""
        oidc_config = Mock()
        oidc_config.authorization_endpoint = "https://auth.example.com/authorize"

        context = OIDCContext(
            issuer_url="https://auth.example.com",
            client_id="test-client",
            client_secret=None,
            scopes=["openid", "profile"],
            redirect_uri="http://localhost:8080/callback",
            oidc_config=oidc_config,
            storage=Mock(),
        )

        pkce = Mock(code_challenge="test-challenge")
        url = context.get_authorization_url("test-state", pkce)

        assert "https://auth.example.com/authorize?" in url
        assert "client_id=test-client" in url
        assert "redirect_uri=http%3A%2F%2Flocalhost%3A8080%2Fcallback" in url
        assert "scope=openid+profile" in url
        assert "state=test-state" in url
        assert "code_challenge=test-challenge" in url
        assert "code_challenge_method=S256" in url

    def test_get_token_refresh_data_with_secret(self):
        """Test token refresh data includes client secret when provided."""
        context = OIDCContext(
            issuer_url="https://auth.example.com",
            client_id="test-client",
            client_secret="test-secret",
            scopes=["openid"],
            redirect_uri="http://localhost:8080/callback",
            oidc_config=Mock(),
            storage=Mock(),
        )

        mock_token = Mock()
        mock_token.refresh_token = "refresh-token-123"
        context.current_tokens = mock_token

        data = context.get_token_refresh_data()

        assert data["grant_type"] == "refresh_token"
        assert data["refresh_token"] == "refresh-token-123"
        assert data["client_id"] == "test-client"
        assert data["client_secret"] == "test-secret"

    def test_get_token_refresh_data_without_secret(self):
        """Test token refresh data excludes client secret when not provided."""
        context = OIDCContext(
            issuer_url="https://auth.example.com",
            client_id="test-client",
            client_secret=None,
            scopes=["openid"],
            redirect_uri="http://localhost:8080/callback",
            oidc_config=Mock(),
            storage=Mock(),
        )

        mock_token = Mock()
        mock_token.refresh_token = "refresh-token-123"
        context.current_tokens = mock_token

        data = context.get_token_refresh_data()

        assert "client_secret" not in data

    def test_update_token_expiry_with_expires_in(self):
        """Test updating token expiry time when expires_in is provided."""
        context = OIDCContext(
            issuer_url="https://auth.example.com",
            client_id="test-client",
            client_secret=None,
            scopes=["openid"],
            redirect_uri="http://localhost:8080/callback",
            oidc_config=Mock(),
            storage=Mock(),
        )

        mock_token = Mock()
        mock_token.expires_in = 3600  # 1 hour

        context.update_token_expiry(mock_token)

        assert context.token_expiry_time is not None
        assert context.token_expiry_time > 0

    def test_update_token_expiry_without_expires_in(self):
        """Test updating token expiry when expires_in is not provided."""
        context = OIDCContext(
            issuer_url="https://auth.example.com",
            client_id="test-client",
            client_secret=None,
            scopes=["openid"],
            redirect_uri="http://localhost:8080/callback",
            oidc_config=Mock(),
            storage=Mock(),
        )

        mock_token = Mock()
        mock_token.expires_in = None

        context.update_token_expiry(mock_token)

        assert context.token_expiry_time is None

    def test_is_token_valid_with_valid_token(self):
        """Test is_token_valid returns True for valid non-expired token."""
        context = OIDCContext(
            issuer_url="https://auth.example.com",
            client_id="test-client",
            client_secret=None,
            scopes=["openid"],
            redirect_uri="http://localhost:8080/callback",
            oidc_config=Mock(),
            storage=Mock(),
        )

        mock_token = Mock()
        mock_token.access_token = "valid-token"
        mock_token.expires_in = 3600
        context.current_tokens = mock_token
        context.update_token_expiry(mock_token)

        assert context.is_token_valid() is True

    def test_can_refresh_token_with_refresh_token(self):
        """Test can_refresh_token returns True when refresh token exists."""
        context = OIDCContext(
            issuer_url="https://auth.example.com",
            client_id="test-client",
            client_secret=None,
            scopes=["openid"],
            redirect_uri="http://localhost:8080/callback",
            oidc_config=Mock(),
            storage=Mock(),
        )

        mock_token = Mock()
        mock_token.refresh_token = "refresh-token-123"
        context.current_tokens = mock_token

        assert context.can_refresh_token() is True


class TestExternalOIDCAuth:
    """Test ExternalOIDCAuth initialization and validation."""

    def test_init_raises_on_missing_issuer_url(self):
        """Test that __init__ raises ValueError when issuer_url is empty."""
        with pytest.raises(ValueError, match="Missing required issuer URL"):
            ExternalOIDCAuth(issuer_url="", client_id="test-client")

    def test_init_raises_on_missing_client_id(self):
        """Test that __init__ raises ValueError when client_id is empty."""
        with pytest.raises(ValueError, match="Missing required client id"):
            ExternalOIDCAuth(issuer_url="https://auth.example.com", client_id="")
