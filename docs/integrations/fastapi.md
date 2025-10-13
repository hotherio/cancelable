# FastAPI Integration

The cancelable library provides seamless integration with FastAPI for building cancellable endpoints.

## Installation

The FastAPI integration is included when you install cancelable:

```bash
uv add hother-cancelable
```

## Basic Usage

### Dependency Injection

```python
from fastapi import FastAPI, Depends
from hother.cancelable.integrations.fastapi import cancellable_dependency
from hother.cancelable import Cancellable

app = FastAPI()

@app.get("/long-operation")
async def long_operation(cancel: Cancellable = Depends(cancellable_dependency)):
    async with cancel:
        # Your long-running operation here
        result = await process_data()
        return {"result": result}
```

### Timeout Configuration

```python
from hother.cancelable.integrations.fastapi import cancellable_dependency

# Create a custom dependency with timeout
def get_cancellable_30s():
    return cancellable_dependency(timeout=30.0)

@app.get("/timeout-operation")
async def timeout_operation(cancel: Cancellable = Depends(get_cancellable_30s)):
    async with cancel:
        # This operation will timeout after 30 seconds
        return await long_computation()
```

## Advanced Usage

### Background Tasks with Cancellation

```python
from fastapi import BackgroundTasks
from hother.cancelable import CancellationToken

# Store tokens for background tasks
background_tokens = {}

@app.post("/start-background-task")
async def start_background_task(background_tasks: BackgroundTasks):
    token = CancellationToken()
    task_id = str(uuid.uuid4())
    background_tokens[task_id] = token
    
    background_tasks.add_task(
        background_worker,
        task_id,
        token
    )
    
    return {"task_id": task_id}

async def background_worker(task_id: str, token: CancellationToken):
    async with Cancellable.with_token(token) as cancel:
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

### Request Cancellation Handling

```python
from starlette.requests import Request

@app.get("/streaming-response")
async def streaming_response(
    request: Request,
    cancel: Cancellable = Depends(cancellable_dependency)
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
3. **Handle cancellation gracefully**: Catch CancelledError and perform cleanup
4. **Monitor operations**: Use the global registry for debugging and monitoring

## Example: File Upload with Progress

```python
from hother.cancelable import Cancellable
from fastapi import UploadFile, File

@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    cancel: Cancellable = Depends(cancellable_dependency)
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
from hother.cancelable import TimeoutCancellation

@app.get("/with-error-handling")
async def with_error_handling(cancel: Cancellable = Depends(cancellable_dependency)):
    try:
        async with cancel:
            result = await some_operation()
            return {"result": result}
    except TimeoutCancellation:
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