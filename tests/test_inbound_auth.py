"""Tests for authful_mcp_proxy.inbound_auth — provider factory dispatch."""

from unittest.mock import patch

import pytest

from authful_mcp_proxy.config import WebConfig
from authful_mcp_proxy.inbound_auth import build_inbound_auth


class TestInboundAuthDispatch:
    """Each WebConfig.auth_provider value should instantiate the matching
    FastMCP provider class with the right per-IdP kwargs.

    The provider classes are patched at the inbound_auth module so we don't
    hit the network for OIDC discovery / JWKS during unit tests.
    """

    def test_keycloak_dispatches_to_KeycloakAuthProvider(self):
        config = WebConfig(
            auth_provider="keycloak",
            base_url="https://mcp.example.com",
            issuer_url="https://kc.example.com/realms/r",
            scopes="openid email",
            audience="mcp-server",
        )
        with patch("authful_mcp_proxy.inbound_auth.KeycloakAuthProvider") as mock_class:
            build_inbound_auth(config)

        mock_class.assert_called_once_with(
            realm_url="https://kc.example.com/realms/r",
            base_url="https://mcp.example.com",
            required_scopes=["openid", "email"],
            audience="mcp-server",
        )

    def test_oidc_dispatches_to_OIDCProxy_with_derived_config_url(self):
        config = WebConfig(
            auth_provider="oidc",
            base_url="https://mcp.example.com",
            issuer_url="https://idp.example.com",
            client_id="cid",
            client_secret="csec",
            scopes="openid",
        )
        with patch("authful_mcp_proxy.inbound_auth.OIDCProxy") as mock_class:
            build_inbound_auth(config)

        mock_class.assert_called_once_with(
            config_url="https://idp.example.com/.well-known/openid-configuration",
            client_id="cid",
            client_secret="csec",
            audience=None,
            required_scopes=["openid"],
            base_url="https://mcp.example.com",
        )

    def test_oidc_strips_trailing_slash_from_issuer(self):
        config = WebConfig(
            auth_provider="oidc",
            base_url="https://mcp.example.com",
            issuer_url="https://idp.example.com/",
            client_id="cid",
        )
        with patch("authful_mcp_proxy.inbound_auth.OIDCProxy") as mock_class:
            build_inbound_auth(config)

        kwargs = mock_class.call_args.kwargs
        assert (
            kwargs["config_url"]
            == "https://idp.example.com/.well-known/openid-configuration"
        )

    def test_aws_cognito_dispatches_to_AWSCognitoProvider(self):
        config = WebConfig(
            auth_provider="aws-cognito",
            base_url="https://mcp.example.com",
            client_id="cid",
            client_secret="csec",
            cognito_user_pool_id="eu-central-1_abc",
            cognito_aws_region="eu-central-1",
            scopes="openid",
        )
        with patch("authful_mcp_proxy.inbound_auth.AWSCognitoProvider") as mock_class:
            build_inbound_auth(config)

        mock_class.assert_called_once_with(
            user_pool_id="eu-central-1_abc",
            aws_region="eu-central-1",
            client_id="cid",
            client_secret="csec",
            required_scopes=["openid"],
            base_url="https://mcp.example.com",
        )

    def test_google_dispatches_to_GoogleProvider(self):
        config = WebConfig(
            auth_provider="google",
            base_url="https://mcp.example.com",
            client_id="cid",
            client_secret="csec",
        )
        with patch("authful_mcp_proxy.inbound_auth.GoogleProvider") as mock_class:
            build_inbound_auth(config)

        mock_class.assert_called_once_with(
            client_id="cid",
            client_secret="csec",
            required_scopes=None,
            base_url="https://mcp.example.com",
        )

    def test_azure_dispatches_to_AzureProvider(self):
        config = WebConfig(
            auth_provider="azure",
            base_url="https://mcp.example.com",
            client_id="cid",
            client_secret="csec",
            azure_tenant_id="tid",
            azure_identifier_uri="api://example",
            scopes="user.read profile",
        )
        with patch("authful_mcp_proxy.inbound_auth.AzureProvider") as mock_class:
            build_inbound_auth(config)

        mock_class.assert_called_once_with(
            client_id="cid",
            client_secret="csec",
            tenant_id="tid",
            identifier_uri="api://example",
            required_scopes=["user.read", "profile"],
            base_url="https://mcp.example.com",
        )

    def test_unknown_provider_raises(self):
        # Bypass dataclass-level Literal validation by mutating after construction.
        config = WebConfig(
            auth_provider="oidc",
            base_url="https://mcp.example.com",
            issuer_url="https://idp.example.com",
            client_id="cid",
        )
        config.auth_provider = "made-up-provider"  # type: ignore[assignment]  # ty: ignore[invalid-assignment]
        with pytest.raises(ValueError, match="Unknown auth_provider"):
            build_inbound_auth(config)
