#!/usr/bin/env python3
"""
HTTP download examples with cancelation support.
"""

import logging
import signal
from pathlib import Path

import anyio
import httpx

from hother.cancelable import Cancelable, CancelationToken, OperationRegistry
from hother.cancelable.integrations.httpx import CancelableHTTPClient, download_file

# Configure logging
logger = logging.getLogger(__name__)


async def example_simple_download():
    """Example: Simple file download with progress."""

    url = "https://httpbin.org/bytes/1048576"  # 1MB of random data
    output_path = Path("/tmp/simple_download.bin")

    async with Cancelable.with_timeout(30.0, name="simple_download") as cancel:
        cancel.on_progress(lambda op_id, msg, meta: print(f"  {msg}"))

        try:
            bytes_downloaded = await download_file(
                url,
                str(output_path),
                cancel,
                chunk_size=8192,
            )

            print(f"  ✅ Downloaded {bytes_downloaded:,} bytes")
            print(f"  📁 Saved to: {output_path}")

            # Cleanup
            output_path.unlink()

        except Exception as e:
            print(f"  ❌ Download failed: {e}")


async def example_multi_file_download():
    """Example: Download multiple files concurrently."""

    files = [
        ("https://httpbin.org/bytes/524288", "/tmp/file1.bin", "512KB"),
        ("https://httpbin.org/bytes/1048576", "/tmp/file2.bin", "1MB"),
        ("https://httpbin.org/bytes/262144", "/tmp/file3.bin", "256KB"),
    ]

    # Shared cancelation token
    token = CancelationToken()

    async def download_with_id(url: str, path: str, size: str, file_id: int):
        """Download a file with ID tracking."""
        cancelable = Cancelable.with_token(token, name=f"download_{file_id}").combine(Cancelable.with_timeout(60.0))

        cancelable.on_progress(lambda op_id, msg, meta: print(f"  File {file_id} ({size}): {msg}"))

        try:
            async with cancelable:
                bytes_down = await download_file(url, path, cancelable)
                return file_id, bytes_down, Path(path)
        except Exception as e:
            print(f"Download {file_id} failed: {e}")
            return file_id, 0, None

    # Download all files
    print("  Starting concurrent downloads...")

    results = []
    async with anyio.create_task_group() as tg:
        # Schedule downloads
        for i, (url, path, size) in enumerate(files):

            async def download_task(url=url, path=path, size=size, file_id=i + 1):
                result = await download_with_id(url, path, size, file_id)
                results.append(result)

            tg.start_soon(download_task)

    # Summary
    print("\n  Download Summary:")
    total_bytes = 0
    for file_id, bytes_down, path in results:
        if path and path.exists():
            print(f"    File {file_id}: {bytes_down:,} bytes")
            total_bytes += bytes_down
            path.unlink()  # Cleanup
        else:
            print(f"    File {file_id}: Failed")

    print(f"  Total downloaded: {total_bytes:,} bytes")


async def example_resumable_download():
    """Example: Resumable download with interruption."""

    # Use a larger file for this demo
    url = "https://httpbin.org/bytes/5242880"  # 5MB
    output_path = Path("/tmp/resumable_download.bin")

    # First attempt - will be interrupted
    print("  Starting download (will interrupt after 2 seconds)...")

    token1 = CancelationToken()

    async def interrupt_download():
        await anyio.sleep(2.0)
        print("  🛑 Interrupting download...")
        await token1.cancel()

    async with anyio.create_task_group() as tg:
        tg.start_soon(interrupt_download)

        try:
            async with Cancelable.with_token(token1, name="download_attempt_1") as cancel:
                await download_file(url, str(output_path), cancel, resume=True)
        except anyio.get_cancelled_exc_class():
            partial_size = output_path.stat().st_size if output_path.exists() else 0
            print(f"  ⏸️  Download interrupted. Downloaded {partial_size:,} bytes")

    # Resume download
    if output_path.exists():
        print("\n  Resuming download...")

        async with Cancelable.with_timeout(30.0, name="download_resume") as cancel:
            cancel.on_progress(lambda op_id, msg, meta: print(f"  {msg}"))

            total_bytes = await download_file(
                url,
                str(output_path),
                cancel,
                resume=True,
            )

            print(f"  ✅ Download completed. Total size: {total_bytes:,} bytes")

            # Cleanup
            output_path.unlink()


async def example_parallel_chunks():
    """Example: Download file in parallel chunks."""

    url = "https://httpbin.org/bytes/2097152"  # 2MB
    output_path = Path("/tmp/parallel_download.bin")
    chunk_count = 4

    async def get_file_size(url: str) -> int:
        """Get file size from headers."""
        async with httpx.AsyncClient() as client:
            response = await client.head(url)
            return int(response.headers.get("content-length", 0))

    async def download_chunk(
        url: str,
        start: int,
        end: int,
        chunk_id: int,
        cancelable: Cancelable,
    ) -> bytes:
        """Download a specific byte range."""
        headers = {"Range": f"bytes={start}-{end}"}

        async with CancelableHTTPClient(cancelable) as client:
            response = await client.get(url, headers=headers)
            data = response.content

            await cancelable.report_progress(
                f"Chunk {chunk_id} downloaded", {"size": len(data), "range": f"{start}-{end}"}
            )

            return data

    # Get file size
    print("  Getting file size...")
    file_size = await get_file_size(url)
    print(f"  File size: {file_size:,} bytes")

    # Calculate chunks
    chunk_size = file_size // chunk_count
    chunks = []

    for i in range(chunk_count):
        start = i * chunk_size
        end = start + chunk_size - 1 if i < chunk_count - 1 else file_size - 1
        chunks.append((start, end, i + 1))

    # Download chunks in parallel
    print(f"  Downloading in {chunk_count} parallel chunks...")

    async with Cancelable.with_timeout(30.0, name="parallel_download") as cancel:
        cancel.on_progress(lambda op_id, msg, meta: print(f"  {msg}"))

        # Download all chunks
        chunk_data = {}

        async with anyio.create_task_group() as tg:
            for start, end, chunk_id in chunks:

                async def download_and_store(s, e, cid):
                    chunk_data[cid] = await download_chunk(url, s, e, cid, cancel)

                tg.start_soon(download_and_store, start, end, chunk_id)

        # Combine chunks
        print("  Combining chunks...")
        with open(output_path, "wb") as f:
            for i in range(1, chunk_count + 1):
                f.write(chunk_data[i])

        final_size = output_path.stat().st_size
        print(f"  ✅ Download complete. Final size: {final_size:,} bytes")

        # Verify
        if final_size == file_size:
            print("  ✓ Size verification passed")
        else:
            print(f"  ✗ Size mismatch! Expected {file_size}, got {final_size}")

        # Cleanup
        output_path.unlink()


async def example_download_with_retry():
    """Example: Download with automatic retry on failure."""

    # Simulate unreliable server
    class FlakyDownloader:
        def __init__(self, failure_rate: float = 0.3):
            self.failure_rate = failure_rate
            self.attempt_count = 0

        async def download(
            self,
            url: str,
            output_path: str,
            cancelable: Cancelable,
        ) -> int:
            """Download with simulated failures."""
            self.attempt_count += 1

            # Simulate failure
            import random

            if random.random() < self.failure_rate and self.attempt_count < 3:
                await anyio.sleep(0.5)  # Simulate some work
                raise httpx.ConnectError("Simulated connection failure")

            # Actual download
            return await download_file(url, output_path, cancelable)

    url = "https://httpbin.org/bytes/1048576"  # 1MB
    output_path = Path("/tmp/retry_download.bin")

    downloader = FlakyDownloader(failure_rate=0.7)
    max_retries = 3
    retry_delay = 1.0

    for attempt in range(max_retries):
        try:
            print(f"\n  Attempt {attempt + 1}/{max_retries}")

            async with Cancelable.with_timeout(30.0, name=f"download_retry_{attempt}") as cancel:
                cancel.on_progress(lambda op_id, msg, meta: print(f"    {msg}"))

                bytes_down = await downloader.download(url, str(output_path), cancel)

                print(f"  ✅ Download successful: {bytes_down:,} bytes")
                output_path.unlink()  # Cleanup
                break

        except (httpx.HTTPError, anyio.get_cancelled_exc_class()) as e:
            print(f"  ❌ Attempt {attempt + 1} failed: {type(e).__name__}: {e}")

            if attempt < max_retries - 1:
                print(f"  ⏳ Retrying in {retry_delay} seconds...")
                await anyio.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
            else:
                print("  ❌ All retry attempts failed")


async def example_download_queue():
    """Example: Download queue with cancelation."""

    # Create download queue
    queue = []
    for i in range(5):
        size = 262144 * (i + 1)  # 256KB, 512KB, etc.
        queue.append(
            {
                "id": i + 1,
                "url": f"https://httpbin.org/bytes/{size}",
                "path": f"/tmp/queue_download_{i + 1}.bin",
                "size": size,
            }
        )

    # Process queue with global cancelation
    registry = OperationRegistry.get_instance()
    completed = []
    failed = []

    async def process_download(item: dict):
        """Process a single download from queue."""
        cancelable = Cancelable(
            name=f"download_queue_{item['id']}",
            register_globally=True,
        )

        try:
            async with cancelable:
                await cancelable.report_progress(f"Starting download {item['id']}")

                bytes_down = await download_file(
                    item["url"],
                    item["path"],
                    cancelable,
                )

                completed.append(item["id"])
                Path(item["path"]).unlink()  # Cleanup

                await cancelable.report_progress(f"Completed download {item['id']}", {"bytes": bytes_down})

        except Exception as e:
            failed.append(item["id"])
            logger.error(f"Download {item['id']} failed: {e}")

    # Process queue with concurrency limit
    print("  Starting download queue processing...")
    print("  Press Ctrl+C to cancel all downloads\n")

    try:
        async with Cancelable.with_signal(signal.SIGINT, name="queue_manager"):
            semaphore = anyio.Semaphore(2)  # Max 2 concurrent downloads

            async with anyio.create_task_group() as tg:
                for item in queue:

                    async def limited_download(item=item):
                        async with semaphore:
                            await process_download(item)

                    tg.start_soon(limited_download)

    except anyio.get_cancelled_exc_class():
        print("\n  🛑 Download queue cancelled!")

        # Cancel all active downloads
        active = await registry.list_operations()
        if active:
            print(f"  Cancelling {len(active)} active downloads...")
            cancelled = await registry.cancel_all()
            print(f"  Cancelled {cancelled} downloads")

    # Summary
    print("\n  Queue Summary:")
    print(f"    Completed: {len(completed)} ({completed})")
    print(f"    Failed: {len(failed)} ({failed})")
    print(f"    Pending: {len(queue) - len(completed) - len(failed)}")


async def main():
    """Run all HTTP download examples."""

    examples = [
        example_simple_download,
        example_multi_file_download,
        example_resumable_download,
        example_parallel_chunks,
        example_download_with_retry,
        example_download_queue,
    ]

    for example in examples:
        try:
            await example()
        except Exception as e:
            logger.error(f"Example failed: {e}", exc_info=True)
        print()


if __name__ == "__main__":
    anyio.run(main)
