# Web Application Examples

Integrate Cancelable with web frameworks like FastAPI.

_Find the complete source in [`examples/03_integrations/`](https://github.com/hotherio/cancelable/tree/main/examples/03_integrations)._

## FastAPI Request-Scoped Cancelation

Automatically cancel operations when clients disconnect.

### Basic Integration

```python
from fastapi import FastAPI, Depends
from hother.cancelable.integrations.fastapi import cancelable_dependency

app = FastAPI()

@app.get("/process")
async def process_data(cancel: Cancelable = Depends(cancelable_dependency)):
    async with cancel:
        # Automatically cancelled on client disconnect
        result = await heavy_computation()
        return result
```

**Run it:**
```bash
python examples/03_integrations/04_fastapi_example.py
```

### Background Tasks

```python
from hother.cancelable import CancelationToken

job_tokens = {}

@app.post("/jobs")
async def start_job():
    job_id = str(uuid.uuid4())
    token = CancelationToken()
    job_tokens[job_id] = token

    asyncio.create_task(run_job(token))
    return {"job_id": job_id}

@app.delete("/jobs/{job_id}")
async def cancel_job(job_id: str):
    if job_id in job_tokens:
        await job_tokens[job_id].cancel("User cancelled")
    return {"status": "cancelled"}
```

## WebSocket Streaming

Real-time data streaming with cancelation:

```python
@app.websocket("/stream")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    async with Cancelable(name="websocket_stream") as cancel:
        try:
            async for data in data_stream:
                await websocket.send_json(data)
        except WebSocketDisconnect:
            # Client disconnected
            pass
```

## Use Cases

- Long-running API requests with timeouts
- Background job systems with cancel buttons
- WebSocket streaming with disconnect handling
- Request-level timeout protection

## Next Steps

- Read [FastAPI Guide](../integrations/fastapi.md) - Detailed integration
