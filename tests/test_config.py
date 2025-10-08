"""Tests for authful_mcp_proxy.config module."""

from authful_mcp_proxy.config import OIDCConfig


class TestOIDCConfig:
    """Test OIDCConfig dataclass."""

    def test_default_values(self):
        """Test that OIDCConfig initializes with None defaults for optional fields."""
        config = OIDCConfig(
            issuer_url="https://auth.example.com", client_id="test-client"
        )

        assert config.issuer_url == "https://auth.example.com"
        assert config.client_id == "test-client"
        assert config.client_secret is None
        assert config.scopes is None
        assert config.redirect_url is None

    def test_partial_initialization(self):
        """Test OIDCConfig with some values set."""
        config = OIDCConfig(
            issuer_url="https://auth.example.com", client_id="test-client"
        )

        assert config.issuer_url == "https://auth.example.com"
        assert config.client_id == "test-client"
        assert config.client_secret is None
        assert config.scopes is None
        assert config.redirect_url is None

    def test_full_initialization(self):
        """Test OIDCConfig with all values set."""
        config = OIDCConfig(
            issuer_url="https://auth.example.com",
            client_id="test-client",
            client_secret="test-secret",
            scopes="openid profile email",
            redirect_url="http://localhost:8080/callback",
        )

        assert config.issuer_url == "https://auth.example.com"
        assert config.client_id == "test-client"
        assert config.client_secret == "test-secret"
        assert config.scopes == "openid profile email"
        assert config.redirect_url == "http://localhost:8080/callback"

    def test_equality(self):
        """Test that two OIDCConfig instances with same values are equal."""
        config1 = OIDCConfig(
            issuer_url="https://auth.example.com", client_id="test-client"
        )
        config2 = OIDCConfig(
            issuer_url="https://auth.example.com", client_id="test-client"
        )

        assert config1 == config2

    def test_inequality(self):
        """Test that two OIDCConfig instances with different values are not equal."""
        config1 = OIDCConfig(
            issuer_url="https://auth.example.com", client_id="test-client"
        )
        config2 = OIDCConfig(
            issuer_url="https://other.example.com", client_id="test-client"
        )

        assert config1 != config2
