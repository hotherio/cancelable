# HTTPX Integration

The cancelable library provides a cancellable HTTP client built on top of HTTPX, enabling you to cancel HTTP requests and handle timeouts gracefully.

## Installation

The HTTPX integration is included when you install cancelable:

```bash
uv add hother-cancelable
```

## Basic Usage

### Cancellable HTTP Client

```python
from hother.cancelable import Cancellable
from hother.cancelable.integrations.httpx import CancellableHTTPClient

async with Cancellable.with_timeout(30.0) as cancel:
    async with CancellableHTTPClient(cancel) as client:
        response = await client.get("https://api.example.com/data")
        data = response.json()
```

### File Downloads with Progress

```python
from hother.cancelable.integrations.httpx import download_file

async with Cancellable.with_timeout(300.0) as cancel:
    cancel.on_progress(
        lambda op_id, msg, meta: print(f"Download: {msg}")
    )
    
    bytes_downloaded = await download_file(
        "https://example.com/large-file.zip",
        "/tmp/large-file.zip",
        cancel,
        resume=True  # Enable resume support
    )
```

## Advanced Features

### Request Cancellation

```python
from hother.cancelable import CancellationToken

# Manual cancellation
token = CancellationToken()

async def download_task():
    async with Cancellable.with_token(token) as cancel:
        async with CancellableHTTPClient(cancel) as client:
            # This request can be cancelled by calling token.cancel()
            response = await client.get("https://example.com/slow-endpoint")
            return response.json()

# In another task/thread
await token.cancel("User requested cancellation")
```

### Streaming Responses

```python
async with Cancellable.with_timeout(60.0) as cancel:
    async with CancellableHTTPClient(cancel) as client:
        async with client.stream("GET", "https://example.com/stream") as response:
            async for chunk in response.aiter_bytes(chunk_size=1024):
                # Process each chunk
                await process_chunk(chunk)
                
                # Cancellation is checked automatically between chunks
```

### Multiple Requests with Shared Cancellation

```python
async with Cancellable.with_timeout(30.0) as cancel:
    async with CancellableHTTPClient(cancel) as client:
        # All requests share the same cancellation context
        responses = await asyncio.gather(
            client.get("https://api1.example.com/data"),
            client.get("https://api2.example.com/data"),
            client.get("https://api3.example.com/data"),
        )
```

## Configuration Options

### Custom HTTPX Client Options

```python
from httpx import Limits

async with Cancellable.with_timeout(30.0) as cancel:
    async with CancellableHTTPClient(
        cancel,
        # All standard HTTPX client options are supported
        base_url="https://api.example.com",
        headers={"Authorization": "Bearer token"},
        limits=Limits(max_keepalive_connections=10),
        http2=True,
    ) as client:
        response = await client.get("/endpoint")
```

### Progress Tracking for Large Downloads

```python
async def download_with_detailed_progress(url: str, path: str):
    async with Cancellable.with_timeout(600.0) as cancel:
        cancel.on_progress(
            lambda op_id, msg, meta: logger.info(
                f"Download progress",
                url=url,
                **meta
            )
        )
        
        total_bytes = await download_file(
            url,
            path,
            cancel,
            chunk_size=1024 * 1024,  # 1MB chunks
            report_interval=10,  # Report every 10 chunks
        )
        
        return total_bytes
```

## Error Handling

### Handling Different Cancellation Scenarios

```python
from hother.cancelable import TimeoutCancellation, ManualCancellation
from httpx import HTTPError

async def resilient_request(url: str):
    try:
        async with Cancellable.with_timeout(30.0) as cancel:
            async with CancellableHTTPClient(cancel) as client:
                response = await client.get(url)
                return response.json()
                
    except TimeoutCancellation:
        logger.error(f"Request timed out: {url}")
        raise
        
    except ManualCancellation as e:
        logger.info(f"Request cancelled: {e.message}")
        raise
        
    except HTTPError as e:
        logger.error(f"HTTP error: {e}")
        raise
```

## Best Practices

1. **Set appropriate timeouts**: Different endpoints may need different timeout values
2. **Use connection pooling**: Reuse the client for multiple requests when possible
3. **Handle partial downloads**: Use the resume feature for large file downloads
4. **Monitor progress**: Attach progress callbacks for long-running downloads

## Example: Parallel Downloads with Cancellation

```python
from hother.cancelable import Cancellable, CancellationToken

async def download_multiple_files(urls: list[str], cancel_token: CancellationToken):
    """Download multiple files with shared cancellation."""
    
    async with Cancellable.with_token(cancel_token) as cancel:
        cancel.on_progress(
            lambda op_id, msg, meta: logger.info(f"{msg}", **meta)
        )
        
        tasks = []
        for i, url in enumerate(urls):
            filename = f"download_{i}.dat"
            task = download_file(url, filename, cancel)
            tasks.append(task)
        
        # All downloads share the same cancellation context
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        successful = sum(1 for r in results if not isinstance(r, Exception))
        logger.info(f"Downloaded {successful}/{len(urls)} files successfully")
        
        return results
```

## Integration with Retry Logic

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10)
)
async def download_with_retry(url: str, path: str):
    async with Cancellable.with_timeout(60.0) as cancel:
        return await download_file(url, path, cancel)
```