# Stream Processing Examples

This guide demonstrates advanced stream processing patterns with the cancelable library.

## Overview

Stream processing with cancellation support is crucial for handling large datasets, real-time data feeds, and long-running data pipelines. The cancelable library provides robust patterns for these scenarios.

## Basic Stream Processing

### Simple Stream Cancellation

```python
from cancelable import Cancellable
import asyncio

async def data_generator():
    """Simulate a data stream."""
    count = 0
    while True:
        await asyncio.sleep(0.1)
        yield f"data_packet_{count}"
        count += 1

async def process_stream():
    async with Cancellable.with_timeout(5.0) as cancel:
        async for packet in cancel.stream(data_generator()):
            print(f"Processing: {packet}")
            # Cancellation checked automatically between iterations
```

### Stream with Progress Reporting

```python
async def process_large_stream():
    async with Cancellable.with_timeout(60.0) as cancel:
        cancel.on_progress(
            lambda op_id, msg, meta: print(f"Stream progress: {msg}")
        )
        
        async for item in cancel.stream(
            fetch_items_from_api(),
            report_interval=100  # Report every 100 items
        ):
            result = await transform_item(item)
            await save_result(result)
```

## Buffered Stream Processing

### Partial Results Recovery

```python
async def recoverable_stream_processing():
    """Process stream with ability to recover partial results."""
    
    async with Cancellable.with_timeout(30.0) as cancel:
        try:
            processed_items = []
            
            async for item in cancel.stream(
                large_dataset_stream(),
                buffer_partial=True  # Enable buffering
            ):
                # Process item
                result = await complex_processing(item)
                processed_items.append(result)
                
                # Optionally save intermediate results
                if len(processed_items) % 10 == 0:
                    await save_checkpoint(processed_items)
            
            return processed_items
            
        except asyncio.CancelledError:
            # Recover partial results
            partial = cancel.context.partial_result
            print(f"Processed {partial['count']} items before cancellation")
            
            # Return what we processed so far
            return processed_items
```

### Windowed Stream Processing

```python
async def windowed_stream_processing():
    """Process stream in fixed-size windows."""
    
    async def process_window(window: list):
        # Process batch of items together
        return await batch_transform(window)
    
    async with Cancellable.with_timeout(120.0) as cancel:
        window = []
        window_size = 50
        
        async for item in cancel.stream(real_time_feed()):
            window.append(item)
            
            if len(window) >= window_size:
                # Process full window
                results = await process_window(window)
                await output_results(results)
                
                # Report progress
                await cancel.report_progress(
                    f"Processed window of {window_size} items",
                    {"window_count": cancel.context.metadata.get("windows", 0) + 1}
                )
                
                # Update metadata
                cancel.context.metadata["windows"] = cancel.context.metadata.get("windows", 0) + 1
                
                # Clear window
                window = []
        
        # Process remaining items
        if window:
            results = await process_window(window)
            await output_results(results)
```

## Parallel Stream Processing

### Fan-Out Pattern

```python
from asyncio import Queue, create_task, gather

async def fan_out_processing():
    """Process stream items in parallel workers."""
    
    async def worker(worker_id: int, queue: Queue, cancel: Cancellable):
        """Process items from queue."""
        while True:
            try:
                # Get item with timeout
                item = await asyncio.wait_for(
                    queue.get(),
                    timeout=1.0
                )
                
                # Process item
                print(f"Worker {worker_id} processing: {item}")
                result = await process_item(item)
                await save_result(result)
                
                queue.task_done()
                
            except asyncio.TimeoutError:
                # Check if we should stop
                if queue.empty() and cancel.is_cancelled:
                    break
    
    async with Cancellable.with_timeout(60.0) as cancel:
        # Create work queue
        queue = Queue(maxsize=100)
        
        # Start workers
        workers = []
        for i in range(5):
            worker_task = create_task(worker(i, queue, cancel))
            workers.append(worker_task)
        
        # Feed items to queue
        async for item in cancel.stream(data_source()):
            await queue.put(item)
        
        # Wait for queue to be processed
        await queue.join()
        
        # Cancel workers
        await cancel.cancel()
        
        # Wait for workers to finish
        await gather(*workers, return_exceptions=True)
```

### Pipeline Pattern

```python
async def stream_pipeline():
    """Multi-stage stream processing pipeline."""
    
    async def stage1_extract(stream):
        """Extract and parse raw data."""
        async for raw_data in stream:
            parsed = await parse_data(raw_data)
            if parsed:
                yield parsed
    
    async def stage2_transform(stream):
        """Transform parsed data."""
        async for parsed_data in stream:
            transformed = await transform_data(parsed_data)
            yield transformed
    
    async def stage3_enrich(stream):
        """Enrich transformed data."""
        async for transformed_data in stream:
            enriched = await enrich_with_metadata(transformed_data)
            yield enriched
    
    async with Cancellable.with_timeout(300.0) as cancel:
        # Build pipeline
        raw_stream = cancel.stream(fetch_raw_data())
        parsed_stream = stage1_extract(raw_stream)
        transformed_stream = stage2_transform(parsed_stream)
        enriched_stream = stage3_enrich(transformed_stream)
        
        # Process final stream
        results = []
        async for final_item in enriched_stream:
            results.append(final_item)
            
            if len(results) % 10 == 0:
                await cancel.report_progress(
                    f"Pipeline processed {len(results)} items"
                )
        
        return results
```

## Real-Time Stream Processing

### Event Stream Processing

```python
async def process_event_stream():
    """Process real-time events with backpressure handling."""
    
    async with Cancellable.with_signal(signal.SIGINT) as cancel:
        cancel.on_cancel(
            lambda ctx: print(f"Shutting down event processor: {ctx.cancel_reason}")
        )
        
        # Track processing rate
        events_processed = 0
        start_time = asyncio.get_event_loop().time()
        
        async for event in cancel.stream(event_source()):
            # Process event
            try:
                await handle_event(event)
                events_processed += 1
                
                # Report metrics periodically
                if events_processed % 1000 == 0:
                    elapsed = asyncio.get_event_loop().time() - start_time
                    rate = events_processed / elapsed
                    
                    await cancel.report_progress(
                        f"Processing rate: {rate:.2f} events/sec",
                        {
                            "events_processed": events_processed,
                            "rate": rate,
                            "elapsed": elapsed
                        }
                    )
                    
            except Exception as e:
                logger.error(f"Error processing event: {e}")
                # Continue processing other events
```

### WebSocket Stream Processing

```python
import aiohttp

async def process_websocket_stream(url: str):
    """Process WebSocket messages with cancellation."""
    
    async with Cancellable.with_timeout(3600.0) as cancel:  # 1 hour timeout
        session = aiohttp.ClientSession()
        
        try:
            async with session.ws_connect(url) as ws:
                cancel.on_cancel(
                    lambda ctx: asyncio.create_task(ws.close())
                )
                
                # Wrap WebSocket messages in cancellable stream
                async def message_generator():
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            yield msg.data
                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            raise Exception(f"WebSocket error: {ws.exception()}")
                
                # Process messages
                async for message in cancel.stream(message_generator()):
                    data = json.loads(message)
                    await process_websocket_data(data)
                    
        finally:
            await session.close()
```

## Advanced Patterns

### Stateful Stream Processing

```python
class StreamAggregator:
    """Stateful stream processor with cancellation support."""
    
    def __init__(self):
        self.state = {
            "count": 0,
            "sum": 0,
            "min": float('inf'),
            "max": float('-inf')
        }
    
    async def process_stream(self, data_stream, cancel_token):
        """Process stream while maintaining state."""
        
        async with Cancellable.with_token(cancel_token) as cancel:
            cancel.on_cancel(
                lambda ctx: print(f"Aggregation stopped: {self.get_summary()}")
            )
            
            async for value in cancel.stream(data_stream):
                # Update state
                self.state["count"] += 1
                self.state["sum"] += value
                self.state["min"] = min(self.state["min"], value)
                self.state["max"] = max(self.state["max"], value)
                
                # Emit periodic summaries
                if self.state["count"] % 100 == 0:
                    await cancel.report_progress(
                        "Aggregation update",
                        self.get_summary()
                    )
    
    def get_summary(self):
        """Get current aggregation summary."""
        if self.state["count"] == 0:
            return {"count": 0}
        
        return {
            "count": self.state["count"],
            "sum": self.state["sum"],
            "average": self.state["sum"] / self.state["count"],
            "min": self.state["min"],
            "max": self.state["max"]
        }
```

### Stream Joining

```python
async def join_streams():
    """Join multiple streams with cancellation."""
    
    async def merge_streams(*streams):
        """Merge multiple async iterators."""
        queue = asyncio.Queue()
        finished = set()
        
        async def consume_stream(stream_id, stream):
            try:
                async for item in stream:
                    await queue.put((stream_id, item))
            finally:
                finished.add(stream_id)
        
        # Start consumers
        tasks = []
        for i, stream in enumerate(streams):
            task = asyncio.create_task(consume_stream(i, stream))
            tasks.append(task)
        
        # Yield merged items
        while len(finished) < len(streams) or not queue.empty():
            try:
                stream_id, item = await asyncio.wait_for(
                    queue.get(), 
                    timeout=0.1
                )
                yield stream_id, item
            except asyncio.TimeoutError:
                continue
        
        # Wait for all tasks
        await asyncio.gather(*tasks)
    
    async with Cancellable.with_timeout(60.0) as cancel:
        # Create multiple streams
        stream1 = cancel.stream(sensor_data_stream("sensor1"))
        stream2 = cancel.stream(sensor_data_stream("sensor2"))
        stream3 = cancel.stream(sensor_data_stream("sensor3"))
        
        # Process merged stream
        async for stream_id, data in merge_streams(stream1, stream2, stream3):
            print(f"Stream {stream_id}: {data}")
            # Process combined data
            await process_sensor_reading(stream_id, data)
```

## Error Handling in Streams

### Resilient Stream Processing

```python
async def resilient_stream_processing():
    """Process stream with error recovery."""
    
    async def process_with_retry(item, max_retries=3):
        """Process item with retry logic."""
        for attempt in range(max_retries):
            try:
                return await process_item(item)
            except Exception as e:
                if attempt == max_retries - 1:
                    logger.error(f"Failed to process {item} after {max_retries} attempts")
                    raise
                await asyncio.sleep(0.5 * (attempt + 1))  # Exponential backoff
    
    async with Cancellable.with_timeout(300.0) as cancel:
        failed_items = []
        successful_count = 0
        
        async for item in cancel.stream(unreliable_data_source()):
            try:
                result = await process_with_retry(item)
                successful_count += 1
                
                # Save result
                await save_result(result)
                
            except Exception as e:
                failed_items.append({
                    "item": item,
                    "error": str(e),
                    "timestamp": asyncio.get_event_loop().time()
                })
                
                # Report failure
                await cancel.report_progress(
                    f"Processing status",
                    {
                        "successful": successful_count,
                        "failed": len(failed_items),
                        "total": successful_count + len(failed_items)
                    }
                )
        
        # Return summary
        return {
            "successful": successful_count,
            "failed": failed_items
        }
```

## Performance Optimization

### Chunked Processing

```python
async def optimized_bulk_processing():
    """Process stream in optimized chunks."""
    
    async def process_chunk(chunk):
        """Process multiple items efficiently."""
        # Bulk operation (e.g., database insert)
        return await bulk_insert(chunk)
    
    async with Cancellable.with_timeout(600.0) as cancel:
        chunk = []
        chunk_size = 1000
        total_processed = 0
        
        async for item in cancel.stream(large_dataset()):
            chunk.append(item)
            
            if len(chunk) >= chunk_size:
                # Process chunk
                await process_chunk(chunk)
                total_processed += len(chunk)
                
                # Report progress
                await cancel.report_progress(
                    f"Processed {total_processed} items",
                    {
                        "total": total_processed,
                        "chunks": total_processed // chunk_size,
                        "rate": total_processed / cancel.context.duration
                    }
                )
                
                # Clear chunk
                chunk = []
        
        # Process remaining items
        if chunk:
            await process_chunk(chunk)
            total_processed += len(chunk)
        
        return total_processed
```

## Best Practices

1. **Use appropriate buffer sizes**: Balance memory usage with performance
2. **Report progress regularly**: Keep users informed during long operations
3. **Handle backpressure**: Use queues with size limits for parallel processing
4. **Process in chunks**: For better performance with bulk operations
5. **Implement error recovery**: Don't let single failures stop entire stream
6. **Clean up resources**: Ensure streams are properly closed on cancellation
7. **Monitor performance**: Track processing rates and adjust accordingly

## Next Steps

- Review the [API Reference](../api_reference.md) for detailed documentation
- Explore Integration examples for specific use cases
- Check out [Patterns](../patterns.md) for more advanced patterns