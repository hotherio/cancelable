"""
Cancelable - Async Cancellation System for Python Streams

A comprehensive, production-ready cancellation system for async operations
with support for timeouts, signals, conditions, and manual cancellation.
"""

from .core.cancellable import Cancellable, current_operation
from .core.exceptions import (
    CancellationError,
    ConditionCancellation,
    ManualCancellation,
    ParentCancellation,
    SignalCancellation,
    TimeoutCancellation,
)
from .core.models import CancellationReason, OperationContext, OperationStatus
from .core.registry import OperationRegistry
from .core.token import CancellationToken
from .utils.decorators import cancellable, with_timeout
from .utils.streams import cancellable_stream

__version__ = "0.1.0"

__all__ = [
    # Models
    "OperationStatus",
    "CancellationReason",
    "OperationContext",
    "CancellationToken",
    # Core
    "Cancellable",
    "OperationRegistry",
    "current_operation",  # Add this
    # Exceptions
    "CancellationError",
    "TimeoutCancellation",
    "ManualCancellation",
    "SignalCancellation",
    "ConditionCancellation",
    "ParentCancellation",
    # Utilities
    "cancellable",
    "with_timeout",
    "cancellable_stream",
]
