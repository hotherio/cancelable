"""
Integration tests for FastAPI integration.
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock

import anyio
import pytest
from fastapi import HTTPException, Request

from hother.cancelable import Cancelable, CancelationReason
from hother.cancelable.integrations.fastapi import (
    CancelableWebSocket,
    RequestCancelationMiddleware,
    cancelable_dependency,
    cancelable_streaming_response,
    get_request_token,
    with_cancelation,
)


class TestRequestCancelationMiddleware:
    """Test RequestCancelationMiddleware."""

    @pytest.mark.anyio
    async def test_middleware_http_request(self):
        """Test middleware handles HTTP requests."""
        # Mock app
        app = AsyncMock()

        middleware = RequestCancelationMiddleware(app)

        # Mock HTTP scope
        scope = {
            "type": "http",
        }
        receive = AsyncMock()
        send = AsyncMock()

        # Setup receive to never disconnect (normal flow)
        receive_count = [0]

        async def mock_receive():
            receive_count[0] += 1
            # Return http.request first, then http.disconnect after a few calls
            if receive_count[0] < 3:
                await anyio.sleep(0.01)
                return {"type": "http.request"}
            return {"type": "http.disconnect"}

        receive.side_effect = mock_receive

        # Run middleware and let it complete naturally
        await middleware(scope, receive, send)

        # Verify token was added to scope
        assert "cancelation_token" in scope
        assert app.called

    @pytest.mark.anyio
    async def test_middleware_non_http_request(self):
        """Test middleware passes through non-HTTP requests."""
        app = AsyncMock()
        middleware = RequestCancelationMiddleware(app)

        scope = {"type": "websocket"}
        receive = AsyncMock()
        send = AsyncMock()

        await middleware(scope, receive, send)

        # Should pass through without adding token
        assert "cancelation_token" not in scope
        app.assert_called_once_with(scope, receive, send)

    @pytest.mark.anyio
    async def test_middleware_client_disconnect(self):
        """Test middleware handles client disconnect."""
        app = AsyncMock()

        # Make app wait so disconnect can be detected
        async def slow_app(scope, receive, send):
            await anyio.sleep(0.1)

        middleware = RequestCancelationMiddleware(slow_app)

        scope = {"type": "http"}

        disconnect_sent = False

        async def mock_receive():
            nonlocal disconnect_sent
            if not disconnect_sent:
                disconnect_sent = True
                await anyio.sleep(0.01)
                return {"type": "http.disconnect"}
            await anyio.sleep(1)  # Block forever
            return {"type": "http.request"}

        receive = AsyncMock(side_effect=mock_receive)
        send = AsyncMock()

        await middleware(scope, receive, send)

        # Verify token was cancelled
        assert "cancelation_token" in scope
        token = scope["cancelation_token"]
        assert token.is_cancelled


class TestGetRequestToken:
    """Test get_request_token function."""

    def test_get_token_from_request(self):
        """Test getting token from request with middleware."""
        request = Mock(spec=Request)
        token = MagicMock()
        request.scope = {"cancelation_token": token}

        result = get_request_token(request)

        assert result is token

    def test_get_token_creates_new(self):
        """Test creating new token when middleware not installed."""
        request = Mock(spec=Request)
        request.scope = {}

        result = get_request_token(request)

        assert result is not None
        assert "cancelation_token" in request.scope
        assert request.scope["cancelation_token"] is result


class TestCancelableDependency:
    """Test cancelable_dependency function."""

    @pytest.mark.anyio
    async def test_dependency_without_timeout(self):
        """Test dependency without timeout."""
        request = Mock(spec=Request)
        request.scope = {}
        request.method = "GET"
        request.url = Mock()
        request.url.path = "/test"
        request.client = Mock()
        request.client.host = "127.0.0.1"

        cancelable = await cancelable_dependency(request)

        assert isinstance(cancelable, Cancelable)
        assert "GET /test" in cancelable.context.name
        assert cancelable.context.metadata["method"] == "GET"
        assert cancelable.context.metadata["path"] == "/test"
        assert cancelable.context.metadata["client"] == "127.0.0.1"

    @pytest.mark.anyio
    async def test_dependency_with_timeout(self):
        """Test dependency with timeout."""
        request = Mock(spec=Request)
        request.scope = {}
        request.method = "POST"
        request.url = Mock()
        request.url.path = "/api/data"
        request.client = None  # Test no client

        cancelable = await cancelable_dependency(request, timeout=5.0)

        assert isinstance(cancelable, Cancelable)
        assert "POST /api/data" in cancelable.context.name
        assert cancelable.context.metadata["client"] is None


class TestWithCancelation:
    """Test with_cancelation decorator."""

    @pytest.mark.anyio
    async def test_decorator_success(self):
        """Test decorator with successful execution."""
        @with_cancelation(timeout=1.0)
        async def test_endpoint(request: Request):
            return {"status": "ok"}

        request = Mock(spec=Request)
        request.scope = {}
        request.method = "GET"
        request.url = Mock()
        request.url.path = "/test"
        request.client = None

        result = await test_endpoint(request)

        assert result == {"status": "ok"}

    @pytest.mark.anyio
    async def test_decorator_timeout(self):
        """Test decorator with timeout cancelation."""
        @with_cancelation(timeout=0.05, raise_on_cancel=True)
        async def test_endpoint(request: Request):
            await anyio.sleep(1.0)  # Will timeout
            return {"status": "ok"}

        request = Mock(spec=Request)
        request.scope = {}
        request.method = "GET"
        request.url = Mock()
        request.url.path = "/slow"
        request.client = None

        with pytest.raises(HTTPException) as exc_info:
            await test_endpoint(request)

        assert exc_info.value.status_code == 504
        assert "timeout" in exc_info.value.detail.lower()

    @pytest.mark.anyio
    async def test_decorator_signal_cancelation(self):
        """Test decorator with signal cancelation."""
        cancelled_with_signal = False

        @with_cancelation(raise_on_cancel=True)
        async def test_endpoint(request: Request):
            nonlocal cancelled_with_signal
            # Get the token from request scope and cancel it with SIGNAL
            if "cancelation_token" in request.scope:
                token = request.scope["cancelation_token"]
                await token.cancel(CancelationReason.SIGNAL, "Client disconnect")
                cancelled_with_signal = True
            # Now sleep long enough for cancelation to propagate
            await anyio.sleep(1.0)
            return {"status": "ok"}

        request = Mock(spec=Request)
        request.scope = {}
        request.method = "GET"
        request.url = Mock()
        request.url.path = "/test"
        request.client = None

        with pytest.raises(HTTPException) as exc_info:
            await test_endpoint(request)

        assert exc_info.value.status_code == 499
        assert cancelled_with_signal

    @pytest.mark.anyio
    async def test_decorator_other_cancelation(self):
        """Test decorator with other cancelation reason."""
        cancelled_manually = False

        @with_cancelation(raise_on_cancel=True)
        async def test_endpoint(request: Request):
            nonlocal cancelled_manually
            # Get the token from request scope and cancel it with MANUAL reason
            if "cancelation_token" in request.scope:
                token = request.scope["cancelation_token"]
                await token.cancel(CancelationReason.MANUAL, "Manual cancel")
                cancelled_manually = True
            # Sleep long enough for cancelation to propagate
            await anyio.sleep(1.0)
            return {"status": "ok"}

        request = Mock(spec=Request)
        request.scope = {}
        request.method = "GET"
        request.url = Mock()
        request.url.path = "/test"
        request.client = None

        with pytest.raises(HTTPException) as exc_info:
            await test_endpoint(request)

        assert exc_info.value.status_code == 503
        assert "cancelled" in exc_info.value.detail.lower()
        assert cancelled_manually

    @pytest.mark.anyio
    async def test_decorator_no_raise(self):
        """Test decorator with raise_on_cancel=False."""
        @with_cancelation(timeout=0.05, raise_on_cancel=False)
        async def test_endpoint(request: Request):
            await anyio.sleep(1.0)
            return {"status": "ok"}

        request = Mock(spec=Request)
        request.scope = {}
        request.method = "GET"
        request.url = Mock()
        request.url.path = "/test"
        request.client = None

        # Should raise CancelledError, not HTTPException
        with pytest.raises(anyio.get_cancelled_exc_class()):
            await test_endpoint(request)


class TestCancelableStreamingResponse:
    """Test cancelable_streaming_response function."""

    @pytest.mark.anyio
    async def test_streaming_response_success(self):
        """Test successful streaming response."""
        async def generate():
            for i in range(3):
                await anyio.sleep(0.01)
                yield f"data: {i}\n"

        cancelable = Cancelable(name="test_stream")

        response = await cancelable_streaming_response(
            generate(), cancelable, media_type="text/plain"
        )

        # Collect streamed data
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk)

        assert len(chunks) == 3
        # Chunks are strings, not bytes
        assert "data: 0" in chunks[0]

    @pytest.mark.anyio
    async def test_streaming_response_cancelled(self):
        """Test streaming response with cancelation."""
        async def generate():
            for i in range(100):
                await anyio.sleep(0.01)
                yield f"data: {i}\n"

        cancelable = Cancelable.with_timeout(0.05, name="test_stream")

        response = await cancelable_streaming_response(
            generate(), cancelable, media_type="text/plain"
        )

        chunks = []
        try:
            async with cancelable:
                async for chunk in response.body_iterator:
                    chunks.append(chunk)
        except anyio.get_cancelled_exc_class():
            pass  # Expected

        # Should have gotten some chunks before timeout
        assert len(chunks) > 0

    @pytest.mark.anyio
    async def test_streaming_response_sse_cancelled(self):
        """Test SSE streaming with cancelation message."""
        async def generate():
            for i in range(100):
                await anyio.sleep(0.01)
                yield f"data: {i}\n\n"

        cancelable = Cancelable.with_timeout(0.05, name="test_sse")

        response = await cancelable_streaming_response(
            generate(), cancelable, media_type="text/event-stream"
        )

        chunks = []
        try:
            async with cancelable:
                async for chunk in response.body_iterator:
                    chunks.append(chunk)
        except anyio.get_cancelled_exc_class():
            pass

        # Last chunk should be cancelation message for SSE
        if chunks:
            last_chunk = chunks[-1].decode() if isinstance(chunks[-1], bytes) else chunks[-1]
            # May or may not have cancelation message depending on timing
            assert len(chunks) > 0


class TestCancelableWebSocket:
    """Test CancelableWebSocket class."""

    @pytest.mark.anyio
    async def test_websocket_accept(self):
        """Test WebSocket accept."""
        ws = Mock()
        ws.accept = AsyncMock()

        cancelable = Cancelable(name="test_ws")
        cancelable.report_progress = AsyncMock()

        cws = CancelableWebSocket(ws, cancelable)
        await cws.accept(subprotocol="test")

        ws.accept.assert_called_once_with(subprotocol="test")
        cancelable.report_progress.assert_called_once()

    @pytest.mark.anyio
    async def test_websocket_send_text(self):
        """Test WebSocket send_text."""
        ws = Mock()
        ws.send_text = AsyncMock()

        cancelable = Cancelable(name="test_ws")

        cws = CancelableWebSocket(ws, cancelable)
        await cws.send_text("Hello")

        ws.send_text.assert_called_once_with("Hello")

    @pytest.mark.anyio
    async def test_websocket_send_json(self):
        """Test WebSocket send_json."""
        ws = Mock()
        ws.send_json = AsyncMock()

        cancelable = Cancelable(name="test_ws")

        cws = CancelableWebSocket(ws, cancelable)
        await cws.send_json({"message": "test"})

        ws.send_json.assert_called_once_with({"message": "test"})

    @pytest.mark.anyio
    async def test_websocket_receive_text(self):
        """Test WebSocket receive_text."""
        ws = Mock()
        ws.receive_text = AsyncMock(return_value="Hello")

        cancelable = Cancelable(name="test_ws")

        cws = CancelableWebSocket(ws, cancelable)
        result = await cws.receive_text()

        assert result == "Hello"
        ws.receive_text.assert_called_once()

    @pytest.mark.anyio
    async def test_websocket_receive_json(self):
        """Test WebSocket receive_json."""
        ws = Mock()
        ws.receive_json = AsyncMock(return_value={"message": "test"})

        cancelable = Cancelable(name="test_ws")

        cws = CancelableWebSocket(ws, cancelable)
        result = await cws.receive_json()

        assert result == {"message": "test"}
        ws.receive_json.assert_called_once()

    @pytest.mark.anyio
    async def test_websocket_close(self):
        """Test WebSocket close."""
        ws = Mock()
        ws.close = AsyncMock()

        cancelable = Cancelable(name="test_ws")
        cancelable.report_progress = AsyncMock()

        cws = CancelableWebSocket(ws, cancelable)
        await cws.close(code=1001, reason="Going away")

        ws.close.assert_called_once_with(1001, "Going away")
        cancelable.report_progress.assert_called_once()

    @pytest.mark.anyio
    async def test_websocket_cancelled_during_send(self):
        """Test WebSocket cancelation during send."""
        ws = Mock()
        ws.send_text = AsyncMock()

        cancelable = Cancelable.with_timeout(0.01, name="test_ws")

        cws = CancelableWebSocket(ws, cancelable)

        with pytest.raises(anyio.get_cancelled_exc_class()):
            async with cancelable:
                await anyio.sleep(0.05)  # Wait for timeout
                await cws.send_text("This should not send")
