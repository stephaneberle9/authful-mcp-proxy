from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from authsome_mcp_proxy import mcp_proxy
from authsome_mcp_proxy.config import DesktopConfig, WebConfig

# ---------------------------------------------------------------------------
# Desktop (stdio) mode
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_async_desktop_relays_server_info():
    """Desktop mode connects once to relay upstream name/version/etc., then
    creates a fresh disconnected client for create_proxy. Transport is stdio."""
    upstream_url = "http://upstream:8080"
    desktop_config = DesktopConfig(
        issuer_url="https://auth.example.com", client_id="test-client"
    )

    # Mock server_info and init_result that behave like Pydantic models
    # with model_dump and extra fields
    class MockModel:
        def __init__(self, data):
            self._data = data
            for k, v in data.items():
                setattr(self, k, v)

        def model_dump(self, exclude=None):
            if exclude is None:
                return self._data.copy()
            return {k: v for k, v in self._data.items() if k not in exclude}

    with patch("authsome_mcp_proxy.mcp_proxy.ExternalOIDCAuth"):
        with patch("authsome_mcp_proxy.mcp_proxy.Client") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client

            server_info_data = {
                "name": "BackendServer",
                "version": "1.2.3",
                "websiteUrl": "https://example.com",
                "icons": [{"uri": "https://example.com/icon.png", "type": "image/png"}],
                "title": "Some Title",
                "custom_info_prop": "info-value",
            }
            mock_server_info = MockModel(server_info_data)

            init_result_data = {
                "serverInfo": mock_server_info,
                "instructions": "Test instructions",
                "custom_init_prop": "init-value",
                "protocolVersion": "2024-11-05",
                "capabilities": {},
            }
            mock_init_result = MockModel(init_result_data)

            mock_client.initialize_result = mock_init_result
            mock_client_cls.return_value = mock_client

            with patch(
                "authsome_mcp_proxy.mcp_proxy.create_proxy"
            ) as mock_create_proxy:
                mock_proxy_server = AsyncMock()
                mock_create_proxy.return_value = mock_proxy_server

                await mcp_proxy.run_async(
                    upstream_url, desktop_config, show_banner=False
                )

                # create_proxy was called with the relayed (filtered) properties
                mock_create_proxy.assert_called_once()
                call_args = mock_create_proxy.call_args
                assert call_args.args[0] == mock_client
                call_kwargs = call_args.kwargs
                assert call_kwargs["name"] == "BackendServer"
                assert call_kwargs["version"] == "1.2.3"
                assert call_kwargs["instructions"] == "Test instructions"
                assert call_kwargs["website_url"] == "https://example.com"
                assert call_kwargs["icons"] == [
                    {"uri": "https://example.com/icon.png", "type": "image/png"}
                ]

                # Unknown props are filtered out so create_proxy doesn't TypeError
                assert "title" not in call_kwargs
                assert "custom_info_prop" not in call_kwargs
                assert "custom_init_prop" not in call_kwargs
                # Desktop mode never passes auth= to the FastMCP proxy server
                assert "auth" not in call_kwargs

                # run_async on the proxy is called with transport="stdio"
                mock_proxy_server.run_async.assert_called_once_with(
                    transport="stdio",
                    show_banner=False,
                )


@pytest.mark.asyncio
async def test_run_async_desktop_uses_fresh_proxy_client():
    """create_proxy receives a fresh disconnected client (not the connected info
    client), so each incoming MCP session gets an isolated upstream connection."""
    upstream_url = "http://upstream:8080"
    desktop_config = DesktopConfig(
        issuer_url="https://auth.example.com", client_id="test-client"
    )

    with patch("authsome_mcp_proxy.mcp_proxy.ExternalOIDCAuth"):
        with patch("authsome_mcp_proxy.mcp_proxy.Client") as mock_client_cls:
            info_client = AsyncMock()
            info_client.__aenter__.return_value = info_client
            info_client.initialize_result = None

            proxy_client = AsyncMock()

            # First Client(...) call → info connection; second → disconnected proxy client.
            mock_client_cls.side_effect = [info_client, proxy_client]

            with patch(
                "authsome_mcp_proxy.mcp_proxy.create_proxy"
            ) as mock_create_proxy:
                mock_proxy_server = AsyncMock()
                mock_create_proxy.return_value = mock_proxy_server

                await mcp_proxy.run_async(
                    upstream_url, desktop_config, show_banner=False
                )

                assert mock_client_cls.call_count == 2
                received_client = mock_create_proxy.call_args.args[0]
                assert received_client is proxy_client
                assert received_client is not info_client


# ---------------------------------------------------------------------------
# Web (http) mode
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_async_web_wires_inbound_and_outbound_auth():
    """Web mode skips the info-relay step, plugs inbound auth into create_proxy
    via auth=, and attaches outbound auth to the per-session Client."""
    upstream_url = "http://upstream:8080"
    web_config = WebConfig(
        inbound_auth_provider="keycloak",
        proxy_base_url="https://mcp.example.com",
        issuer_url="https://kc.example.com/realms/r",
    )

    sentinel_inbound = MagicMock(name="inbound_auth")
    sentinel_outbound = MagicMock(name="outbound_auth")

    with (
        patch(
            "authsome_mcp_proxy.mcp_proxy.build_inbound_auth",
            return_value=sentinel_inbound,
        ) as mock_build_inbound,
        patch(
            "authsome_mcp_proxy.mcp_proxy.build_outbound_auth",
            return_value=sentinel_outbound,
        ) as mock_build_outbound,
        patch("authsome_mcp_proxy.mcp_proxy.Client") as mock_client_cls,
        patch("authsome_mcp_proxy.mcp_proxy.create_proxy") as mock_create_proxy,
    ):
        proxy_client = AsyncMock()
        mock_client_cls.return_value = proxy_client

        mock_proxy_server = AsyncMock()
        mock_create_proxy.return_value = mock_proxy_server

        await mcp_proxy.run_async(upstream_url, web_config, show_banner=False)

        # Inbound + outbound factories called exactly once each with the config.
        mock_build_inbound.assert_called_once_with(web_config)
        mock_build_outbound.assert_called_once_with(web_config)

        # The (single) Client was built with auth=outbound_auth (no info-relay
        # connection in web mode).
        assert mock_client_cls.call_count == 1
        client_kwargs = mock_client_cls.call_args.kwargs
        assert client_kwargs["auth"] is sentinel_outbound

        # create_proxy received that client + auth=inbound_auth.
        mock_create_proxy.assert_called_once()
        cp_args = mock_create_proxy.call_args
        assert cp_args.args[0] is proxy_client
        assert cp_args.kwargs["auth"] is sentinel_inbound
        # No server-identity kwargs leak through when none were configured;
        # FastMCP's defaults apply.
        assert "name" not in cp_args.kwargs
        assert "version" not in cp_args.kwargs
        assert "instructions" not in cp_args.kwargs
        assert "website_url" not in cp_args.kwargs

        # Transport is forced to http in web mode.
        mock_proxy_server.run_async.assert_called_once_with(
            transport="http", show_banner=False
        )


@pytest.mark.asyncio
async def test_run_async_web_forwards_server_identity_kwargs():
    """Operator-configured proxy_name/version/instructions/website_url land on
    create_proxy as the matching kwargs, so the proxy advertises them to
    downstream MCP clients instead of FastMCP's auto-generated name."""
    web_config = WebConfig(
        inbound_auth_provider="keycloak",
        proxy_base_url="https://mcp.example.com",
        issuer_url="https://kc.example.com/realms/r",
        proxy_name="ANALYZE",
        proxy_version="2.3.0",
        proxy_instructions="Use these tools for traceability analysis.",
        proxy_website_url="https://analyze.example.com",
    )

    with (
        patch(
            "authsome_mcp_proxy.mcp_proxy.build_inbound_auth", return_value=MagicMock()
        ),
        patch(
            "authsome_mcp_proxy.mcp_proxy.build_outbound_auth", return_value=MagicMock()
        ),
        patch("authsome_mcp_proxy.mcp_proxy.Client"),
        patch("authsome_mcp_proxy.mcp_proxy.create_proxy") as mock_create_proxy,
    ):
        mock_proxy_server = AsyncMock()
        mock_create_proxy.return_value = mock_proxy_server

        await mcp_proxy.run_async("http://upstream:8080", web_config, show_banner=False)

        cp_kwargs = mock_create_proxy.call_args.kwargs
        assert cp_kwargs["name"] == "ANALYZE"
        assert cp_kwargs["version"] == "2.3.0"
        assert cp_kwargs["instructions"] == "Use these tools for traceability analysis."
        assert cp_kwargs["website_url"] == "https://analyze.example.com"


@pytest.mark.asyncio
async def test_run_async_web_omits_unset_server_identity_kwargs():
    """When only some server-identity fields are set, only those are passed."""
    web_config = WebConfig(
        inbound_auth_provider="keycloak",
        proxy_base_url="https://mcp.example.com",
        issuer_url="https://kc.example.com/realms/r",
        proxy_name="ANALYZE",  # only this one set
    )

    with (
        patch(
            "authsome_mcp_proxy.mcp_proxy.build_inbound_auth", return_value=MagicMock()
        ),
        patch(
            "authsome_mcp_proxy.mcp_proxy.build_outbound_auth", return_value=MagicMock()
        ),
        patch("authsome_mcp_proxy.mcp_proxy.Client"),
        patch("authsome_mcp_proxy.mcp_proxy.create_proxy") as mock_create_proxy,
    ):
        mock_proxy_server = AsyncMock()
        mock_create_proxy.return_value = mock_proxy_server

        await mcp_proxy.run_async("http://upstream:8080", web_config, show_banner=False)

        cp_kwargs = mock_create_proxy.call_args.kwargs
        assert cp_kwargs["name"] == "ANALYZE"
        assert "version" not in cp_kwargs
        assert "instructions" not in cp_kwargs
        assert "website_url" not in cp_kwargs


@pytest.mark.asyncio
async def test_run_async_web_forwards_transport_kwargs():
    """host/port/log_level transport_kwargs are forwarded verbatim to FastMCP."""
    upstream_url = "http://upstream:8080"
    web_config = WebConfig(
        inbound_auth_provider="keycloak",
        proxy_base_url="https://mcp.example.com",
        issuer_url="https://kc.example.com/realms/r",
    )

    with (
        patch(
            "authsome_mcp_proxy.mcp_proxy.build_inbound_auth", return_value=MagicMock()
        ),
        patch(
            "authsome_mcp_proxy.mcp_proxy.build_outbound_auth", return_value=MagicMock()
        ),
        patch("authsome_mcp_proxy.mcp_proxy.Client"),
        patch("authsome_mcp_proxy.mcp_proxy.create_proxy") as mock_create_proxy,
    ):
        mock_proxy_server = AsyncMock()
        mock_create_proxy.return_value = mock_proxy_server

        await mcp_proxy.run_async(
            upstream_url,
            web_config,
            show_banner=False,
            host="0.0.0.0",
            port=8000,
            log_level="DEBUG",
        )

        mock_proxy_server.run_async.assert_called_once_with(
            transport="http",
            show_banner=False,
            host="0.0.0.0",
            port=8000,
            log_level="DEBUG",
        )


# ---------------------------------------------------------------------------
# Unrecognised config type
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_async_rejects_unknown_config_type():
    """Anything that's neither DesktopConfig nor WebConfig is a TypeError."""

    class NotAConfig:
        pass

    with pytest.raises(TypeError, match="Unsupported config type"):
        await mcp_proxy.run_async(
            "http://upstream:8080",
            NotAConfig(),  # ty: ignore[invalid-argument-type]
            show_banner=False,
        )
