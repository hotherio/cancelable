"""
FastAPI integration for request-scoped cancellation.
"""

from collections.abc import AsyncIterator, Callable
from typing import Any

import anyio
from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse

from hother.cancelable.core.cancelable import Cancelable
from hother.cancelable.core.models import CancelationReason
from hother.cancelable.core.token import CancelationToken
from hother.cancelable.utils.logging import get_logger

logger = get_logger(__name__)


class RequestCancelationMiddleware:
    """
    FastAPI middleware that provides request-scoped cancellation.
    """

    def __init__(self, app, default_timeout: float | None = None):
        """
        Initialize middleware.

        Args:
            app: FastAPI application
            default_timeout: Default timeout for all requests
        """
        self.app = app
        self.default_timeout = default_timeout

    async def __call__(self, scope, receive, send):
        """ASGI middleware implementation."""
        if scope["type"] == "http":
            # Create cancellation token for this request
            token = CancelationToken()
            scope["cancellation_token"] = token

            # Monitor for client disconnect
            async def monitor_disconnect():
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        await token.cancel(CancelationReason.SIGNAL, "Client disconnected")
                        break

            # Run app with monitoring
            async with anyio.create_task_group() as tg:
                tg.start_soon(monitor_disconnect)
                await self.app(scope, receive, send)
        else:
            await self.app(scope, receive, send)


def get_request_token(request: Request) -> CancelationToken:
    """
    Get cancellation token from request.

    Args:
        request: FastAPI request

    Returns:
        Cancelation token for this request
    """
    if hasattr(request, "scope") and "cancellation_token" in request.scope:
        return request.scope["cancellation_token"]

    # Create new token if middleware not installed
    token = CancelationToken()
    request.scope["cancellation_token"] = token
    return token


async def cancelable_dependency(
    request: Request,
    timeout: float | None = None,
) -> Cancelable:
    """
    FastAPI dependency that provides a cancellable for the request.

    Args:
        request: FastAPI request
        timeout: Optional timeout override

    Returns:
        Cancelable instance for this request

    Example:
        @app.get("/data")
        async def get_data(
            cancel: Cancelable = Depends(cancellable_dependency)
        ):
            async with cancel:
                return await fetch_data()
    """
    token = get_request_token(request)

    # Create base cancellable with token
    name = f"{request.method} {request.url.path}"
    metadata = {
        "method": request.method,
        "path": request.url.path,
        "client": request.client.host if request.client else None,
    }

    base_cancellable = Cancelable.with_token(token, name=name, metadata=metadata)

    # Add timeout if specified
    if timeout:
        timeout_cancellable = Cancelable.with_timeout(timeout, name=f"timeout_{timeout}s")
        # Combine but preserve the original name and metadata
        combined = base_cancellable.combine(timeout_cancellable)
        combined.context.name = name  # Override the combined name
        combined.context.metadata.update(metadata)  # Preserve the original metadata
        return combined

    return base_cancellable


def with_cancelation(
    timeout: float | None = None,
    raise_on_cancel: bool = True,
) -> Callable:
    """
    Decorator for FastAPI endpoints with automatic cancellation.

    Args:
        timeout: Optional timeout for the endpoint
        raise_on_cancel: Whether to raise HTTPException on cancellation

    Returns:
        Decorator function

    Example:
        @app.get("/slow")
        @with_cancellation(timeout=30.0)
        async def slow_endpoint(request: Request):
            # Cancelable is automatically injected
            cancellable = current_operation()
            await long_operation()
    """

    def decorator(func: Callable) -> Callable:
        async def wrapper(request: Request, *args, **kwargs):
            cancellable = await cancellable_dependency(request, timeout)

            try:
                async with cancellable:
                    return await func(request, *args, **kwargs)

            except anyio.get_cancelled_exc_class():
                if raise_on_cancel:
                    if cancellable.context.cancel_reason == CancelationReason.TIMEOUT:
                        raise HTTPException(status_code=504, detail="Request timeout")
                    if cancellable.context.cancel_reason == CancelationReason.SIGNAL:
                        raise HTTPException(status_code=499, detail="Client closed connection")
                    raise HTTPException(status_code=503, detail=f"Request cancelled: {cancellable.context.cancel_message}")
                raise

        return wrapper

    return decorator


async def cancelable_streaming_response(
    generator: AsyncIterator[Any],
    cancellable: Cancelable,
    media_type: str = "text/plain",
    chunk_size: int | None = None,
) -> StreamingResponse:
    """
    Create a streaming response with cancellation support.

    Args:
        generator: Async generator producing response chunks
        cancellable: Cancelable instance
        media_type: Response media type
        chunk_size: Optional chunk size hint

    Returns:
        FastAPI StreamingResponse

    Example:
        @app.get("/stream")
        async def stream_data(cancel: Cancelable = Depends(cancellable_dependency)):
            async def generate():
                for i in range(1000):
                    await anyio.sleep(0.1)
                    yield f"data: {i}\n\n"

            return await cancellable_streaming_response(
                generate(),
                cancel,
                media_type="text/event-stream"
            )
    """

    async def wrapped_generator():
        try:
            async for chunk in cancellable.stream(generator):
                yield chunk
        except anyio.get_cancelled_exc_class():
            # Handle cancellation gracefully
            logger.info(
                "Streaming response cancelled",
                operation_id=cancellable.context.id,
                cancel_reason=cancellable.context.cancel_reason,
            )
            # Optionally yield a final message
            if media_type == "text/event-stream":
                yield "event: cancelled\ndata: Stream cancelled\n\n"

    return StreamingResponse(
        wrapped_generator(),
        media_type=media_type,
    )


# WebSocket support
class CancelableWebSocket:
    """
    WebSocket wrapper with cancellation support.
    """

    def __init__(self, websocket, cancellable: Cancelable):
        self.websocket = websocket
        self.cancellable = cancellable

    async def accept(self, **kwargs):
        """Accept WebSocket connection."""
        await self.websocket.accept(**kwargs)
        await self.cancellable.report_progress("WebSocket connected")

    async def send_text(self, data: str):
        """Send text with cancellation check."""
        await self.cancellable._token.check_async()
        await self.websocket.send_text(data)

    async def send_json(self, data: Any):
        """Send JSON with cancellation check."""
        await self.cancellable._token.check_async()
        await self.websocket.send_json(data)

    async def receive_text(self) -> str:
        """Receive text with cancellation check."""
        await self.cancellable._token.check_async()
        return await self.websocket.receive_text()

    async def receive_json(self) -> Any:
        """Receive JSON with cancellation check."""
        await self.cancellable._token.check_async()
        return await self.websocket.receive_json()

    async def close(self, code: int = 1000, reason: str = ""):
        """Close WebSocket connection."""
        await self.websocket.close(code, reason)
        await self.cancellable.report_progress("WebSocket closed")
