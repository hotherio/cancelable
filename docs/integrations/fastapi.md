# FastAPI Integration

The cancelable library provides seamless integration with FastAPI for building cancelable endpoints.

## Installation

The FastAPI integration is included when you install cancelable:

```bash
uv add hother-cancelable
```

## Basic Usage

### Dependency Injection

```python
from fastapi import FastAPI, Depends
from hother.cancelable.integrations.fastapi import cancelable_dependency
from hother.cancelable import Cancelable

app = FastAPI()

@app.get("/long-operation")
async def long_operation(cancel: Cancelable = Depends(cancelable_dependency)):
    async with cancel:
        # Your long-running operation here
        result = await process_data()
        return {"result": result}
```

### Timeout Configuration

```python
from hother.cancelable.integrations.fastapi import cancelable_dependency

# Create a custom dependency with timeout
def get_cancellable_30s():
    return cancelable_dependency(timeout=30.0)

@app.get("/timeout-operation")
async def timeout_operation(cancel: Cancelable = Depends(get_cancellable_30s)):
    async with cancel:
        # This operation will timeout after 30 seconds
        return await long_computation()
```

## Advanced Usage

### Background Tasks with Cancelation

```python
from fastapi import BackgroundTasks
from hother.cancelable import CancelationToken

# Store tokens for background tasks
background_tokens = {}

@app.post("/start-background-task")
async def start_background_task(background_tasks: BackgroundTasks):
    token = CancelationToken()
    task_id = str(uuid.uuid4())
    background_tokens[task_id] = token
    
    background_tasks.add_task(
        background_worker,
        task_id,
        token
    )
    
    return {"task_id": task_id}

async def background_worker(task_id: str, token: CancelationToken):
    async with Cancelable.with_token(token) as cancel:
        try:
            # Long-running background work
            await process_large_dataset()
        finally:
            # Cleanup
            background_tokens.pop(task_id, None)

@app.post("/cancel-task/{task_id}")
async def cancel_task(task_id: str):
    token = background_tokens.get(task_id)
    if token:
        await token.cancel()
        return {"status": "cancelled"}
    return {"status": "not_found"}
```

### Request Cancelation Handling

```python
from starlette.requests import Request

@app.get("/streaming-response")
async def streaming_response(
    request: Request,
    cancel: Cancelable = Depends(cancelable_dependency)
):
    async def generate():
        async with cancel:
            for i in range(100):
                # Check if client disconnected
                if await request.is_disconnected():
                    await cancel.cancel()
                    break
                
                yield f"data: Item {i}\n\n"
                await asyncio.sleep(0.1)
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream"
    )
```

## Best Practices

1. **Always use async with**: Ensure proper cleanup by using the context manager
2. **Set appropriate timeouts**: Configure timeouts based on expected operation duration
3. **Handle cancelation gracefully**: Catch CancelledError and perform cleanup
4. **Monitor operations**: Use the global registry for debugging and monitoring

## Example: File Upload with Progress

```python
from hother.cancelable import Cancelable
from fastapi import UploadFile, File

@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    cancel: Cancelable = Depends(cancelable_dependency)
):
    async with cancel:
        cancel.on_progress(
            lambda op_id, msg, meta: logger.info(f"Upload progress: {msg}")
        )
        
        total_size = 0
        chunk_size = 1024 * 1024  # 1MB chunks
        
        with open(f"uploads/{file.filename}", "wb") as f:
            while chunk := await file.read(chunk_size):
                f.write(chunk)
                total_size += len(chunk)
                
                await cancel.report_progress(
                    f"Uploaded {total_size} bytes",
                    {"bytes": total_size, "filename": file.filename}
                )
        
        return {
            "filename": file.filename,
            "size": total_size,
            "status": "completed"
        }
```

## Error Handling

```python
from hother.cancelable import TimeoutCancelation

@app.get("/with-error-handling")
async def with_error_handling(cancel: Cancelable = Depends(cancelable_dependency)):
    try:
        async with cancel:
            result = await some_operation()
            return {"result": result}
    except TimeoutCancelation:
        return JSONResponse(
            status_code=408,
            content={"error": "Operation timed out"}
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )
```

## Middleware

### RequestCancelationMiddleware

ASGI middleware for automatic request cancelation monitoring:

```python
from fastapi import FastAPI
from hother.cancelable.integrations.fastapi import RequestCancelationMiddleware

app = FastAPI()

# Add middleware
app.add_middleware(RequestCancelationMiddleware)

@app.post("/process")
async def process_data(data: dict):
    # Automatically cancels if client disconnects
    # No need for manual cancelable_dependency
    async with Cancelable(name="process") as cancel:
        result = await long_operation(data)
        return {"result": result}
```

**Benefits**:
- Automatic client disconnect detection
- Application-wide cancelation monitoring
- No per-endpoint setup needed

## WebSocket Support

### CancelableWebSocket

WebSocket wrapper with built-in cancelation support:

```python
from fastapi import WebSocket
from hother.cancelable.integrations.fastapi import CancelableWebSocket

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await websocket.accept()

    async with Cancelable.with_timeout(300.0) as cancel:
        ws = CancelableWebSocket(websocket, cancel)

        # Send with cancelation checking
        await ws.send_json({"status": "connected"})

        # Receive with cancelation checking
        while True:
            data = await ws.receive_json()

            # Report progress
            await cancel.report_progress(f"Received from {client_id}")

            response = await process(data)
            await ws.send_json(response)
```

**Methods**:
- `send_text(data)`, `send_json(data)` - Send with cancelation check
- `receive_text()`, `receive_json()` - Receive with cancelation check
- Auto-integrates with progress reporting

## SSE Streaming

### cancelable_streaming_response()

Create Server-Sent Events (SSE) streaming responses with cancelation:

```python
from hother.cancelable.integrations.fastapi import cancelable_streaming_response

@app.get("/stream/progress/{job_id}")
async def stream_progress(job_id: str):
    async def generate():
        async with Cancelable(name=f"stream_{job_id}") as cancel:
            for i in range(100):
                # Checks cancelation before each event
                yield f"data: Processing {i}/100\n\n"
                await anyio.sleep(0.5)

    return cancelable_streaming_response(generate())
```

**Features**:
- SSE format support
- Automatic cancelation checking
- Graceful stream termination
- Client disconnect handling

## Exception Handling

### with_cancelation Decorator

Automatic exception handling for FastAPI endpoints:

```python
from hother.cancelable.integrations.fastapi import with_cancelation

@app.post("/process")
@with_cancelation  # Converts cancelation to proper HTTP status
async def process_data(data: dict):
    async with Cancelable.with_timeout(30.0) as cancel:
        result = await long_operation(data)
        return {"result": result}

# If cancelled: automatically returns HTTP 499 (Client Closed Request)
# If timeout: automatically returns HTTP 504 (Gateway Timeout)
```

**HTTP status codes**:
- `CancelationReason.TIMEOUT` → 504 Gateway Timeout
- `CancelationReason.MANUAL` → 499 Client Closed Request
- `CancelationReason.SIGNAL` → 503 Service Unavailable
- Other → 500 Internal Server Error