"""
Tests for library integrations.
"""

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from hother.cancelable import Cancelable, CancelationToken

# Check for optional dependencies at module level
try:
    import fastapi
    _has_fastapi = True
except ImportError:
    _has_fastapi = False


@pytest.mark.skipif(not _has_fastapi, reason="fastapi not installed")
class TestFastAPIIntegration:
    """Test FastAPI integration."""

    def test_request_cancelation_middleware(self):
        """Test RequestCancelationMiddleware."""
        from hother.cancelable.integrations.fastapi import RequestCancelationMiddleware

        # Mock FastAPI app
        mock_app = Mock()

        middleware = RequestCancelationMiddleware(mock_app, default_timeout=30.0)

        assert middleware.app is mock_app
        assert middleware.default_timeout == 30.0

    @pytest.mark.anyio
    async def test_get_request_token(self):
        """Test getting cancelation token from request."""
        from hother.cancelable.integrations.fastapi import get_request_token

        # Mock request with token
        mock_request = Mock()
        mock_request.scope = {"cancelation_token": CancelationToken()}

        token = get_request_token(mock_request)
        assert isinstance(token, CancelationToken)
        assert token is mock_request.scope["cancelation_token"]

        # Mock request without token
        mock_request2 = Mock()
        mock_request2.scope = {}

        token2 = get_request_token(mock_request2)
        assert isinstance(token2, CancelationToken)
        assert mock_request2.scope["cancelation_token"] is token2

    @pytest.mark.anyio
    async def test_cancellable_dependency(self):
        """Test cancelable_dependency for FastAPI."""
        from hother.cancelable.integrations.fastapi import cancelable_dependency

        # Mock request
        mock_request = Mock()
        mock_request.method = "GET"
        mock_request.url = Mock(path="/test")
        mock_request.client = Mock(host="127.0.0.1")
        mock_request.scope = {}

        cancelable = await cancelable_dependency(mock_request, timeout=5.0)

        assert isinstance(cancelable, Cancelable)
        assert cancelable.context.name == "GET /test"
        assert cancelable.context.metadata["method"] == "GET"
        assert cancelable.context.metadata["path"] == "/test"
        assert cancelable.context.metadata["client"] == "127.0.0.1"

    def test_with_cancelation_decorator(self):
        """Test with_cancelation decorator."""
        from hother.cancelable.integrations.fastapi import with_cancelation

        @with_cancelation(timeout=10.0)
        async def test_endpoint(request):
            return {"status": "ok"}

        # Verify decorator doesn't break the function
        assert asyncio.iscoroutinefunction(test_endpoint)

    @pytest.mark.anyio
    async def test_cancellable_websocket(self):
        """Test CancelableWebSocket wrapper."""
        from hother.cancelable.integrations.fastapi import CancelableWebSocket

        # Mock WebSocket
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_text = AsyncMock()
        mock_ws.send_json = AsyncMock()
        mock_ws.receive_text = AsyncMock(return_value="test message")
        mock_ws.receive_json = AsyncMock(return_value={"key": "value"})
        mock_ws.close = AsyncMock()

        cancelable = Cancelable(name="websocket_test")
        ws = CancelableWebSocket(mock_ws, cancelable)

        async with cancelable:
            # Test methods
            await ws.accept()
            await ws.send_text("hello")
            await ws.send_json({"msg": "data"})
            text = await ws.receive_text()
            json_data = await ws.receive_json()
            await ws.close()

        # Verify calls
        mock_ws.accept.assert_called_once()
        mock_ws.send_text.assert_called_once_with("hello")
        mock_ws.send_json.assert_called_once_with({"msg": "data"})
        mock_ws.receive_text.assert_called_once()
        mock_ws.receive_json.assert_called_once()
        mock_ws.close.assert_called_once()

        assert text == "test message"
        assert json_data == {"key": "value"}

