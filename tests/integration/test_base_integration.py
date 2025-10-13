"""
Tests for library integrations.
"""

import asyncio
import os
import tempfile
from unittest.mock import AsyncMock, Mock

import anyio
import httpx
import pytest

from hother.cancelable import Cancellable, CancellationToken


class TestHTTPXIntegration:
    """Test HTTPX integration."""

    @pytest.mark.anyio
    async def test_cancellable_client_basic(self):
        """Test basic CancellableHTTPClient usage."""
        from hother.cancelable.integrations.httpx import CancellableHTTPClient

        # Mock response
        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.content = b"test content"

        # Mock client
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.request.return_value = mock_response
        mock_client.aclose = AsyncMock()

        cancellable = Cancellable(name="http_test")
        client = CancellableHTTPClient(cancellable=cancellable)
        client.client = mock_client  # Replace with mock

        async with cancellable:
            async with client:
                response = await client.get("https://example.com")
                assert response.status_code == 200

        mock_client.request.assert_called_once_with("GET", "https://example.com")
        mock_client.aclose.assert_called_once()

    @pytest.mark.anyio
    async def test_cancellable_client_cancellation(self):
        """Test HTTP request cancellation."""
        from hother.cancelable.integrations.httpx import CancellableHTTPClient

        # Mock client that delays
        mock_client = AsyncMock(spec=httpx.AsyncClient)

        async def delayed_request(*args, **kwargs):
            await anyio.sleep(1.0)
            return Mock(status_code=200)

        mock_client.request = delayed_request
        mock_client.aclose = AsyncMock()

        cancellable = Cancellable.with_timeout(0.1)
        client = CancellableHTTPClient(cancellable=cancellable)
        client.client = mock_client

        with pytest.raises(anyio.get_cancelled_exc_class()):
            async with cancellable:
                async with client:
                    await client.get("https://example.com")

        assert cancellable.is_cancelled

    @pytest.mark.anyio
    async def test_download_file(self):
        """Test file download with cancellation."""
        from hother.cancelable.integrations.httpx import download_file

        # Create a mock streaming response
        class MockResponse:
            headers = {"content-length": "1000"}

            async def aiter_bytes(self, chunk_size):
                for i in range(10):
                    yield b"x" * 100
                    await anyio.sleep(0.01)

            def raise_for_status(self):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        # Mock client
        mock_client = Mock()
        mock_client.stream = Mock(return_value=MockResponse())  # Return the response directly

        # Patch CancellableHTTPClient
        from hother.cancelable.integrations import httpx as httpx_integration

        original_client = httpx_integration.CancellableHTTPClient

        class MockCancellableClient:
            def __init__(self, cancellable):
                self.cancellable = cancellable

            async def __aenter__(self):
                return mock_client

            async def __aexit__(self, *args):
                pass

        httpx_integration.CancellableHTTPClient = MockCancellableClient

        try:
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                tmp_path = tmp.name

            cancellable = Cancellable(name="download_test")

            async with cancellable:
                bytes_downloaded = await download_file("https://example.com/file", tmp_path, cancellable, chunk_size=100)

            assert bytes_downloaded == 1000
            assert os.path.exists(tmp_path)

            # Verify file content
            with open(tmp_path, "rb") as f:
                content = f.read()
                assert len(content) == 1000
                assert content == b"x" * 1000

        finally:
            # Restore original
            httpx_integration.CancellableHTTPClient = original_client

            # Cleanup
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    @pytest.mark.anyio
    async def test_streaming_response(self):
        """Test streaming response with cancellation."""
        from hother.cancelable.integrations.httpx import CancellableHTTPClient

        # Mock streaming response
        class MockStreamResponse:
            def __init__(self):
                self.status_code = 200

            def raise_for_status(self):
                pass

            async def aiter_bytes(self, chunk_size=None):
                for i in range(10):
                    yield f"chunk_{i}".encode()
                    await anyio.sleep(0.01)

            async def aiter_text(self, chunk_size=None):
                for i in range(10):
                    yield f"chunk_{i}"
                    await anyio.sleep(0.01)

            async def aiter_lines(self):
                for i in range(10):
                    yield f"line_{i}"
                    await anyio.sleep(0.01)

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        # Create a proper mock client that supports async context manager
        class MockClient:
            def stream(self, method, url, **kwargs):
                return MockStreamResponse()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def aclose(self):
                pass

        cancellable = Cancellable.with_timeout(0.05)
        client = CancellableHTTPClient(cancellable=cancellable)
        client.client = MockClient()

        chunks = []

        with pytest.raises(anyio.get_cancelled_exc_class()):
            async with cancellable:
                async with client:
                    async with client.stream("GET", "https://example.com") as response:
                        async for chunk in response.aiter_bytes():
                            chunks.append(chunk)

        # Should have collected some chunks before timeout
        assert len(chunks) > 0
        assert len(chunks) < 10  # But not all


class TestFastAPIIntegration:
    """Test FastAPI integration."""

    def test_request_cancellation_middleware(self):
        """Test RequestCancellationMiddleware."""
        from hother.cancelable.integrations.fastapi import RequestCancellationMiddleware

        # Mock FastAPI app
        mock_app = Mock()

        middleware = RequestCancellationMiddleware(mock_app, default_timeout=30.0)

        assert middleware.app is mock_app
        assert middleware.default_timeout == 30.0

    @pytest.mark.anyio
    async def test_get_request_token(self):
        """Test getting cancellation token from request."""
        from hother.cancelable.integrations.fastapi import get_request_token

        # Mock request with token
        mock_request = Mock()
        mock_request.scope = {"cancellation_token": CancellationToken()}

        token = get_request_token(mock_request)
        assert isinstance(token, CancellationToken)
        assert token is mock_request.scope["cancellation_token"]

        # Mock request without token
        mock_request2 = Mock()
        mock_request2.scope = {}

        token2 = get_request_token(mock_request2)
        assert isinstance(token2, CancellationToken)
        assert mock_request2.scope["cancellation_token"] is token2

    @pytest.mark.anyio
    async def test_cancellable_dependency(self):
        """Test cancellable_dependency for FastAPI."""
        from hother.cancelable.integrations.fastapi import cancellable_dependency

        # Mock request
        mock_request = Mock()
        mock_request.method = "GET"
        mock_request.url = Mock(path="/test")
        mock_request.client = Mock(host="127.0.0.1")
        mock_request.scope = {}

        cancellable = await cancellable_dependency(mock_request, timeout=5.0)

        assert isinstance(cancellable, Cancellable)
        assert cancellable.context.name == "GET /test"
        assert cancellable.context.metadata["method"] == "GET"
        assert cancellable.context.metadata["path"] == "/test"
        assert cancellable.context.metadata["client"] == "127.0.0.1"

    def test_with_cancellation_decorator(self):
        """Test with_cancellation decorator."""
        from hother.cancelable.integrations.fastapi import with_cancellation

        @with_cancellation(timeout=10.0)
        async def test_endpoint(request):
            return {"status": "ok"}

        # Verify decorator doesn't break the function
        assert asyncio.iscoroutinefunction(test_endpoint)

    @pytest.mark.anyio
    async def test_cancellable_websocket(self):
        """Test CancellableWebSocket wrapper."""
        from hother.cancelable.integrations.fastapi import CancellableWebSocket

        # Mock WebSocket
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_text = AsyncMock()
        mock_ws.send_json = AsyncMock()
        mock_ws.receive_text = AsyncMock(return_value="test message")
        mock_ws.receive_json = AsyncMock(return_value={"key": "value"})
        mock_ws.close = AsyncMock()

        cancellable = Cancellable(name="websocket_test")
        ws = CancellableWebSocket(mock_ws, cancellable)

        async with cancellable:
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


class TestSQLAlchemyIntegration:
    """Test SQLAlchemy integration."""

    @pytest.mark.anyio
    async def test_cancellable_session_basic(self):
        """Test basic CancellableAsyncSession usage."""
        from hother.cancelable.integrations.sqlalchemy import CancellableAsyncSession

        # Mock SQLAlchemy session
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=Mock())
        mock_session.scalar = AsyncMock(return_value=42)
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        cancellable = Cancellable(name="db_test")
        session = CancellableAsyncSession(mock_session, cancellable)

        async with cancellable:
            # Test execute
            result = await session.execute("SELECT 1")
            assert result is not None

            # Test scalar
            value = await session.scalar("SELECT COUNT(*)")
            assert value == 42

            # Test commit
            await session.commit()

        mock_session.execute.assert_called_once()
        mock_session.scalar.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.anyio
    async def test_cancellable_session_cancellation(self):
        """Test session cancellation."""
        from hother.cancelable.integrations.sqlalchemy import CancellableAsyncSession

        # Mock slow query
        async def slow_execute(*args, **kwargs):
            await anyio.sleep(1.0)
            return Mock()

        mock_session = AsyncMock()
        mock_session.execute = slow_execute

        cancellable = Cancellable.with_timeout(0.1)
        session = CancellableAsyncSession(mock_session, cancellable)

        with pytest.raises(anyio.get_cancelled_exc_class()):
            async with cancellable:
                await session.execute("SELECT SLEEP(10)")

        assert cancellable.is_cancelled

    @pytest.mark.anyio
    async def test_bulk_operations(self):
        """Test bulk operations with progress."""
        from hother.cancelable.integrations.sqlalchemy import CancellableAsyncSession

        # Track progress reports
        progress_reports = []

        def capture_progress(op_id, msg, meta):
            progress_reports.append((msg, meta))

        # Mock session
        mock_session = AsyncMock()
        mock_session.bulk_insert_mappings = AsyncMock()

        cancellable = Cancellable().on_progress(capture_progress)
        session = CancellableAsyncSession(mock_session, cancellable)

        # Test bulk insert
        mappings = [{"id": i, "value": f"val_{i}"} for i in range(2500)]

        async with cancellable:
            await session.bulk_insert_mappings(Mock(), mappings)

        # Should have progress reports
        assert len(progress_reports) > 0
        assert "Starting bulk insert of 2500 records" in progress_reports[0][0]
        assert mock_session.bulk_insert_mappings.call_count == 3  # 3 batches

    @pytest.mark.anyio
    async def test_transaction_context(self):
        """Test CancellableTransaction context manager."""
        from hother.cancelable.integrations.sqlalchemy import CancellableTransaction

        # Mock session and transaction
        mock_transaction = AsyncMock()
        mock_transaction.commit = AsyncMock()
        mock_transaction.rollback = AsyncMock()

        mock_session = AsyncMock()
        mock_session.session = AsyncMock()
        mock_session.session.begin = AsyncMock(return_value=mock_transaction)

        cancellable = Cancellable()
        mock_session.cancellable = cancellable

        # Test successful transaction
        async with CancellableTransaction(mock_session):
            pass

        mock_transaction.commit.assert_called_once()
        mock_transaction.rollback.assert_not_called()

        # Test failed transaction
        mock_transaction.commit.reset_mock()
        mock_transaction.rollback.reset_mock()

        with pytest.raises(ValueError):
            async with CancellableTransaction(mock_session):
                raise ValueError("Test error")

        mock_transaction.commit.assert_not_called()
        mock_transaction.rollback.assert_called_once()

    @pytest.mark.anyio
    async def test_execute_chunked(self):
        """Test execute_chunked utility."""
        from hother.cancelable.integrations.sqlalchemy import execute_chunked

        # Mock query results
        chunks = [
            [Mock(id=i) for i in range(0, 5)],
            [Mock(id=i) for i in range(5, 10)],
            [Mock(id=i) for i in range(10, 13)],
        ]

        chunk_index = 0

        async def mock_execute(query):
            nonlocal chunk_index
            if chunk_index < len(chunks):
                result = Mock()
                result.scalars().all.return_value = chunks[chunk_index]
                chunk_index += 1
                return result
            else:
                result = Mock()
                result.scalars().all.return_value = []
                return result

        # Mock session
        mock_session = AsyncMock()
        mock_session.execute = mock_execute
        mock_session.cancellable = Cancellable()

        # Process chunks
        processed_items = []

        async def process_chunk(items):
            processed_items.extend(items)

        mock_query = Mock()
        mock_query.limit.return_value.offset.return_value = mock_query

        total = await execute_chunked(mock_session, mock_query, chunk_size=5, process_chunk=process_chunk)

        assert total == 13
        assert len(processed_items) == 13


@pytest.mark.anyio
class TestEndToEndIntegration:
    """Test end-to-end integration scenarios."""

    async def test_http_with_db_operations(self):
        """Test combining HTTP and database operations."""
        from hother.cancelable.integrations.httpx import CancellableHTTPClient
        from hother.cancelable.integrations.sqlalchemy import CancellableAsyncSession

        # Create shared cancellable
        async with Cancellable.with_timeout(5.0, name="full_operation") as cancel:
            cancel.on_progress(lambda op_id, msg, meta: print(f"Progress: {msg}"))

            # Mock HTTP client
            http_client = CancellableHTTPClient(cancellable=cancel)
            http_client.client = AsyncMock()
            http_client.client.request = AsyncMock(return_value=Mock(status_code=200, json=lambda: {"data": [1, 2, 3]}))
            http_client.client.aclose = AsyncMock()

            # Mock DB session
            db_session = AsyncMock()
            db_session.execute = AsyncMock()
            db_session.commit = AsyncMock()

            cancellable_session = CancellableAsyncSession(db_session, cancel)

            # Fetch data via HTTP
            async with http_client:
                response = await http_client.get("https://api.example.com/data")
                data = response.json()

            # Store in database
            for item in data["data"]:
                await cancellable_session.execute(f"INSERT INTO items VALUES ({item})")

            await cancellable_session.commit()

            # Report completion
            await cancel.report_progress("Operation completed successfully")

        assert cancel.is_completed
        assert not cancel.is_cancelled

    async def test_cascading_cancellation(self):
        """Test cancellation propagating through integrations."""
        token = CancellationToken()

        async def integrated_operation():
            from hother.cancelable.integrations.httpx import CancellableHTTPClient

            async with Cancellable.with_token(token, name="integrated") as cancel:
                # Mock slow HTTP operation
                client = CancellableHTTPClient(cancellable=cancel)
                client.client = AsyncMock()

                async def slow_request(*args, **kwargs):
                    await anyio.sleep(1.0)
                    return Mock(status_code=200)

                client.client.request = slow_request
                client.client.aclose = AsyncMock()

                async with client:
                    await client.get("https://example.com")

        # Start operation and cancel it
        async with anyio.create_task_group() as tg:
            tg.start_soon(integrated_operation)

            # Cancel after short delay
            await anyio.sleep(0.1)
            await token.cancel()

        assert token.is_cancelled
