"""
FastAPI integration for request-scoped cancelation.
"""

from collections.abc import AsyncIterator, Callable
from typing import Any

import anyio
from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from hother.cancelable.core.cancelable import Cancelable
from hother.cancelable.core.models import CancelationReason
from hother.cancelable.core.token import CancelationToken
from hother.cancelable.utils.logging import get_logger

logger = get_logger(__name__)


class RequestCancelationMiddleware:
    """
    FastAPI middleware that provides request-scoped cancelation.
    """

    def __init__(self, app: ASGIApp, default_timeout: float | None = None):
        """
        Initialize middleware.

        Args:
            app: ASGI application
            default_timeout: Default timeout for all requests
        """
        self.app = app
        self.default_timeout = default_timeout

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI middleware implementation."""
        if scope["type"] == "http":
            # Create cancelation token for this request
            token = CancelationToken()
            scope["cancelation_token"] = token

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
    Get cancelation token from request.

    Args:
        request: FastAPI request

    Returns:
        Cancelation token for this request
    """
    if hasattr(request, "scope") and "cancelation_token" in request.scope:
        return request.scope["cancelation_token"]

    # Create new token if middleware not installed
    token = CancelationToken()
    request.scope["cancelation_token"] = token
    return token


async def cancelable_dependency(
    request: Request,
    timeout: float | None = None,
) -> Cancelable:
    """
    FastAPI dependency that provides a cancelable for the request.

    Args:
        request: FastAPI request
        timeout: Optional timeout override

    Returns:
        Cancelable instance for this request

    Example:
        @app.get("/data")
        async def get_data(
            cancel: Cancelable = Depends(cancelable_dependency)
        ):
            async with cancel:
                return await fetch_data()
    """
    token = get_request_token(request)

    # Create base cancelable with token
    name = f"{request.method} {request.url.path}"
    metadata: dict[str, str | None] = {
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
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Decorator for FastAPI endpoints with automatic cancelation.

    Args:
        timeout: Optional timeout for the endpoint
        raise_on_cancel: Whether to raise HTTPException on cancelation

    Returns:
        Decorator function

    Example:
        @app.get("/slow")
        @with_cancelation(timeout=30.0)
        async def slow_endpoint(request: Request):
            # Cancelable is automatically injected
            cancelable = current_operation()
            await long_operation()
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        async def wrapper(request: Request, *args: Any, **kwargs: Any):
            cancelable = await cancelable_dependency(request, timeout)

            try:
                async with cancelable:
                    return await func(request, *args, **kwargs)

            except anyio.get_cancelled_exc_class():
                if raise_on_cancel:
                    if cancelable.context.cancel_reason == CancelationReason.TIMEOUT:
                        raise HTTPException(status_code=504, detail="Request timeout")
                    if cancelable.context.cancel_reason == CancelationReason.SIGNAL:
                        raise HTTPException(status_code=499, detail="Client closed connection")
                    raise HTTPException(
                        status_code=503, detail=f"Request cancelled: {cancelable.context.cancel_message}"
                    )
                raise

        return wrapper

    return decorator


async def cancelable_streaming_response(
    generator: AsyncIterator[Any],
    cancelable: Cancelable,
    media_type: str = "text/plain",
    chunk_size: int | None = None,
) -> StreamingResponse:
    """
    Create a streaming response with cancelation support.

    Args:
        generator: Async generator producing response chunks
        cancelable: Cancelable instance
        media_type: Response media type
        chunk_size: Optional chunk size hint

    Returns:
        FastAPI StreamingResponse

    Example:
        @app.get("/stream")
        async def stream_data(cancel: Cancelable = Depends(cancelable_dependency)):
            async def generate():
                for i in range(1000):
                    await anyio.sleep(0.1)
                    yield f"data: {i}\n\n"

            return await cancelable_streaming_response(
                generate(),
                cancel,
                media_type="text/event-stream"
            )
    """

    async def wrapped_generator():
        try:
            async for chunk in cancelable.stream(generator):
                yield chunk
        except anyio.get_cancelled_exc_class():
            # Handle cancelation gracefully
            logger.info(
                "Streaming response cancelled",
                extra={
                    "operation_id": cancelable.context.id,
                    "cancel_reason": cancelable.context.cancel_reason,
                },
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
    WebSocket wrapper with cancelation support.
    """

    def __init__(self, websocket: Any, cancelable: Cancelable):
        self.websocket = websocket
        self.cancelable = cancelable

    async def accept(self, **kwargs: Any):
        """Accept WebSocket connection."""
        await self.websocket.accept(**kwargs)
        await self.cancelable.report_progress("WebSocket connected")

    async def send_text(self, data: str):
        """Send text with cancelation check."""
        await self.cancelable.check_cancelation()
        await self.websocket.send_text(data)

    async def send_json(self, data: Any):
        """Send JSON with cancelation check."""
        await self.cancelable.check_cancelation()
        await self.websocket.send_json(data)

    async def receive_text(self) -> str:
        """Receive text with cancelation check."""
        await self.cancelable.check_cancelation()
        return await self.websocket.receive_text()

    async def receive_json(self) -> Any:
        """Receive JSON with cancelation check."""
        await self.cancelable.check_cancelation()
        return await self.websocket.receive_json()

    async def close(self, code: int = 1000, reason: str = ""):
        """Close WebSocket connection."""
        await self.websocket.close(code, reason)
        await self.cancelable.report_progress("WebSocket closed")
