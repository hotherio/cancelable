"""
Shared test fixtures and utilities for the cancelable test suite.
"""

import asyncio
import time
from contextlib import asynccontextmanager
from typing import Optional

import pytest


# Configure anyio to use only asyncio backend for now
@pytest.fixture(params=["asyncio"])
def anyio_backend(request):
    """Provide the backend for anyio tests."""
    return request.param


@asynccontextmanager
async def assert_cancelled_within(timeout: float, tolerance: float = 0.5):
    """
    Context manager to assert that code is cancelled within a specific timeframe.
    
    Args:
        timeout: Expected timeout in seconds
        tolerance: Acceptable deviation from expected timeout (default 0.5s)
    """
    start_time = time.time()
    
    try:
        yield
    except asyncio.CancelledError:
        # This is expected
        elapsed = time.time() - start_time
        assert elapsed < timeout + tolerance, f"Cancelation took {elapsed:.2f}s, expected < {timeout + tolerance}s"
        assert elapsed > timeout - tolerance, f"Cancelation took {elapsed:.2f}s, expected > {timeout - tolerance}s"
        raise  # Re-raise to maintain expected behavior
    else:
        pytest.fail(f"Expected CancelledError within {timeout}s, but none was raised")


@pytest.fixture
async def clean_registry():
    """Fixture that provides a clean OperationRegistry and cleans up after test."""
    from hother.cancelable.core.registry import OperationRegistry
    
    # Clear the singleton instance before test
    OperationRegistry._instance = None
    
    # Get a fresh registry
    registry = OperationRegistry.get_instance()
    
    yield registry
    
    # Cleanup after test
    await registry.clear_all()
    OperationRegistry._instance = None