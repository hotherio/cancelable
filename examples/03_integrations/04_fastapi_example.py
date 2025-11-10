#!/usr/bin/env python3
"""
FastAPI integration example with request-scoped cancelation.

This example demonstrates how to use the FastAPI integration for
request-scoped cancelation, dependency injection, and streaming responses.
"""

# --8<-- [start:imports]
import asyncio
import time
from collections.abc import AsyncGenerator

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

from hother.cancelable import Cancelable
from hother.cancelable.integrations.fastapi import (
    RequestCancelationMiddleware,
    cancelable_dependency,
    cancelable_streaming_response,
    get_request_token,
    with_cancelation,
)

# --8<-- [end:imports]

# --8<-- [start:app_setup]
# Create FastAPI app
app = FastAPI(title="Cancelable FastAPI Example")

# Add cancelation middleware
app.add_middleware(RequestCancelationMiddleware)
# --8<-- [end:app_setup]


# --8<-- [start:basic_endpoint]
@app.get("/")
async def root():
    """Basic endpoint."""
    return {"message": "FastAPI with cancelation support"}


@app.get("/slow-operation")
async def slow_operation(request: Request):
    """Endpoint with cancelable operation."""
    # Get cancelation token for this request
    token = get_request_token(request)
    cancel = Cancelable.with_token(token, name="slow_operation")

    print(f"Starting operation for request {cancel.context.id}")

    try:
        # Simulate work that can be cancelled
        for i in range(10):
            await cancel.report_progress(f"Processing step {i + 1}/10")
            await asyncio.sleep(0.5)

        await cancel.report_progress("Operation completed")
        return {"status": "completed", "steps": 10}

    except asyncio.CancelledError:
        print(f"Operation cancelled for request {cancel.context.id}")
        raise HTTPException(status_code=499, detail="Request cancelled")


@app.get("/timeout-operation")
async def timeout_operation(request: Request):
    """Endpoint with timeout."""
    # Get cancelation token and add timeout
    token = get_request_token(request)
    timeout_cancel = Cancelable.with_timeout(3.0, name="timeout_operation")
    cancel = timeout_cancel.combine(Cancelable.with_token(token))

    print(f"Starting timeout operation (3s) for request {cancel.context.id}")

    try:
        for i in range(10):
            await cancel.report_progress(f"Working... {i + 1}/10")
            await asyncio.sleep(0.5)

        return {"status": "completed"}

    except asyncio.CancelledError:
        print(f"Timeout operation cancelled for request {cancel.context.id}")
        raise HTTPException(status_code=504, detail="Request timeout")


# --8<-- [end:basic_endpoint]


# --8<-- [start:decorator_endpoint]
@app.get("/decorated-endpoint")
@with_cancelation(timeout=5.0)
async def decorated_endpoint(request: Request):
    """Endpoint using the @with_cancelation decorator."""
    print("Decorated endpoint called")

    # The decorator automatically handles cancelation - if cancelled,
    # it will raise an HTTPException. We just need to do our work.
    for i in range(8):
        print(f"Decorated step {i + 1}/8")
        await asyncio.sleep(0.3)

    return {"status": "decorated_completed"}


# --8<-- [end:decorator_endpoint]


# --8<-- [start:streaming]
@app.get("/stream-data")
async def stream_data(request: Request):
    """Basic streaming endpoint with manual cancelation checks."""
    token = get_request_token(request)

    async def generate_data() -> AsyncGenerator[str, None]:
        """Generate streaming data."""
        for i in range(20):
            # Check for cancelation
            if token.is_cancelled:
                yield "event: cancelled\ndata: Stream cancelled\n\n"
                break

            yield f"data: {i}\n\n"
            await asyncio.sleep(0.2)

    return StreamingResponse(generate_data(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.get("/cancelable-stream")
async def cancellable_stream_endpoint(cancel: Cancelable = Depends(cancelable_dependency)):
    """Advanced streaming endpoint using cancelable_streaming_response."""

    async def generate_data() -> AsyncGenerator[str, None]:
        """Generate streaming data with automatic cancelation."""
        for i in range(20):
            await cancel.report_progress(f"Streaming item {i}")
            yield f"data: {i}\n\n"
            await asyncio.sleep(0.2)

    return await cancelable_streaming_response(generate_data(), cancel, media_type="text/event-stream")


# --8<-- [end:streaming]


@app.get("/concurrent-operations")
async def concurrent_operations(request: Request):
    """Demonstrate concurrent operations with shared cancelation."""
    token = get_request_token(request)

    async def worker(worker_id: int):
        """Worker task with cancelation support."""
        try:
            for i in range(5):
                if token.is_cancelled:
                    raise asyncio.CancelledError()
                await asyncio.sleep(0.4)
            return f"worker_{worker_id}_completed"
        except asyncio.CancelledError:
            return f"worker_{worker_id}_cancelled"

    # Run multiple workers concurrently
    tasks = [asyncio.create_task(worker(i)) for i in range(3)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    return {"status": "concurrent_completed", "results": [str(r) for r in results]}


@app.get("/manual-token")
async def manual_token(request: Request):
    """Example using get_request_token directly."""
    token = get_request_token(request)

    # Simulate some work
    for i in range(5):
        if token.is_cancelled:
            raise HTTPException(status_code=499, detail="Request cancelled")
        await asyncio.sleep(0.2)

    return {"status": "manual_token_completed"}


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": time.time()}


if __name__ == "__main__":
    print("This example demonstrates FastAPI integration with cancelation.")
    print("To run the server, install uvicorn and run:")
    print("  pip install uvicorn")
    print("  uvicorn examples.03_integrations.04_fastapi_example:app --host 0.0.0.0 --port 8000")
    print()
    print("Available endpoints:")
    print("  GET / - Basic endpoint")
    print("  GET /slow-operation - Cancelable operation")
    print("  GET /timeout-operation - Operation with timeout")
    print("  GET /decorated-endpoint - Using @with_cancelation decorator")
    print("  GET /stream-data - Basic streaming")
    print("  GET /cancelable-stream - Advanced streaming")
    print("  GET /concurrent-operations - Concurrent operations")
    print("  GET /manual-token - Manual token usage")
    print()
    print("Test cancelation by closing connections or using timeouts!")
