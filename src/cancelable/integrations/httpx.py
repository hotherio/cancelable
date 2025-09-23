"""
HTTPX integration for cancellable HTTP requests.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx

from cancelable.core.cancellable import Cancellable
from cancelable.core.token import CancellationToken
from cancelable.utils.logging import get_logger

logger = get_logger(__name__)


class CancellableHTTPClient:
    """
    HTTPX async client wrapper with cancellation support.
    """

    def __init__(
        self,
        cancellable: Cancellable | None = None,
        token: CancellationToken | None = None,
        **httpx_kwargs,
    ):
        """
        Initialize cancellable HTTP client.

        Args:
            cancellable: Cancellable instance to use
            token: Cancellation token (alternative to cancellable)
            **httpx_kwargs: Arguments passed to httpx.AsyncClient
        """
        self.cancellable = cancellable
        self.token = token or (cancellable._token if cancellable else None)
        self.client = httpx.AsyncClient(**httpx_kwargs)
        self._closed = False

    async def __aenter__(self) -> "CancellableHTTPClient":
        """Enter context manager."""
        await self.client.__aenter__()
        return self

    async def __aexit__(self, *args) -> None:
        """Exit context manager."""
        await self.close()

    async def close(self) -> None:
        """Close the HTTP client."""
        if not self._closed:
            await self.client.aclose()
            self._closed = True

    async def request(
        self,
        method: str,
        url: str,
        *,
        cancellable: Cancellable | None = None,
        **kwargs,
    ) -> httpx.Response:
        """
        Make an HTTP request with cancellation support.

        Args:
            method: HTTP method
            url: Request URL
            cancellable: Override default cancellable
            **kwargs: Additional arguments for httpx

        Returns:
            HTTP response

        Raises:
            CancelledError: If request is cancelled
        """
        # Use provided cancellable or default
        cancel = cancellable or self.cancellable

        if cancel:
            await cancel._token.check_async()
            await cancel.report_progress(f"Starting {method} request to {url}")

        try:
            response = await self.client.request(method, url, **kwargs)

            if cancel:
                await cancel.report_progress(f"Completed {method} request", {"status_code": response.status_code, "url": str(url)})

            return response

        except httpx.RequestError as e:
            if cancel:
                await cancel.report_progress(f"Request failed: {type(e).__name__}", {"error": str(e)})
            raise

    async def get(self, url: str, **kwargs) -> httpx.Response:
        """GET request with cancellation."""
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs) -> httpx.Response:
        """POST request with cancellation."""
        return await self.request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs) -> httpx.Response:
        """PUT request with cancellation."""
        return await self.request("PUT", url, **kwargs)

    async def delete(self, url: str, **kwargs) -> httpx.Response:
        """DELETE request with cancellation."""
        return await self.request("DELETE", url, **kwargs)

    @asynccontextmanager
    async def stream(
        self,
        method: str,
        url: str,
        *,
        cancellable: Cancellable | None = None,
        chunk_size: int | None = None,
        **kwargs,
    ) -> AsyncIterator[httpx.Response]:
        """
        Stream response with cancellation support.

        Args:
            method: HTTP method
            url: Request URL
            cancellable: Override default cancellable
            chunk_size: Size of chunks to read
            **kwargs: Additional arguments for httpx

        Yields:
            Streaming HTTP response
        """
        cancel = cancellable or self.cancellable

        if cancel:
            await cancel._token.check_async()

        response = self.client.stream(method, url, **kwargs)
        async with response as resp:
            resp.raise_for_status()

            # Create a wrapped response with cancellable iteration
            if cancel:
                # Wrap the iteration methods
                original_aiter_bytes = resp.aiter_bytes
                original_aiter_text = resp.aiter_text
                original_aiter_lines = resp.aiter_lines

                resp.aiter_bytes = lambda chunk_size=chunk_size: self._wrap_stream(
                    lambda: original_aiter_bytes(chunk_size) if chunk_size else original_aiter_bytes(),
                    cancel,
                    chunk_size,
                )
                resp.aiter_text = lambda chunk_size=chunk_size: self._wrap_stream(
                    lambda: original_aiter_text(chunk_size) if chunk_size else original_aiter_text(),
                    cancel,
                    chunk_size,
                )
                resp.aiter_lines = lambda: self._wrap_stream(
                    original_aiter_lines,
                    cancel,
                    None,  # No chunk size for lines
                )

            yield resp

    async def _wrap_stream(
        self,
        stream_factory,
        cancellable: Cancellable,
        chunk_size: int | None,
    ):
        """Wrap a stream method with cancellation checking."""
        byte_count = 0
        chunk_count = 0

        async for chunk in stream_factory():
            # Check cancellation
            await cancellable._token.check_async()

            yield chunk

            # Track progress
            chunk_count += 1
            if isinstance(chunk, bytes):
                byte_count += len(chunk)

            # Report progress periodically
            if chunk_count % 100 == 0:
                await cancellable.report_progress("Streaming data", {"chunks": chunk_count, "bytes": byte_count})


async def download_file(
    url: str,
    output_path: str,
    cancellable: Cancellable,
    chunk_size: int = 8192,
    resume: bool = True,
) -> int:
    """
    Download a file with cancellation and resume support.

    Args:
        url: URL to download from
        output_path: Path to save file
        cancellable: Cancellable instance
        chunk_size: Size of chunks to download
        resume: Whether to resume partial downloads

    Returns:
        Total bytes downloaded

    Example:
        async with Cancellable.with_timeout(300) as cancel:
            bytes_downloaded = await download_file(
                "https://example.com/large.zip",
                "/tmp/large.zip",
                cancel
            )
    """
    import os

    import aiofiles

    # Check if we should resume
    start_byte = 0
    if resume and os.path.exists(output_path):
        start_byte = os.path.getsize(output_path)
        logger.info(f"Resuming download from byte {start_byte}")

    headers = {}
    if start_byte > 0:
        headers["Range"] = f"bytes={start_byte}-"

    async with CancellableHTTPClient(cancellable) as client:
        async with client.stream("GET", url, headers=headers) as response:
            # Get total size
            content_length = response.headers.get("content-length")
            total_size = int(content_length) + start_byte if content_length else None

            if total_size:
                await cancellable.report_progress("Starting download", {"total_bytes": total_size, "resume_byte": start_byte})

            # Open file in append mode if resuming
            mode = "ab" if start_byte > 0 else "wb"
            downloaded = start_byte

            async with aiofiles.open(output_path, mode) as f:
                async for chunk in response.aiter_bytes(chunk_size):
                    await f.write(chunk)
                    downloaded += len(chunk)

                    # Report progress
                    if total_size:
                        progress = (downloaded / total_size) * 100
                        await cancellable.report_progress(
                            f"Downloading: {progress:.1f}%",
                            {
                                "downloaded_bytes": downloaded,
                                "total_bytes": total_size,
                                "progress_percent": progress,
                            },
                        )

            await cancellable.report_progress("Download completed", {"total_bytes": downloaded})

            return downloaded
