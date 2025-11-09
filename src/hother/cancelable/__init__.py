"""
Cancelable - Async Cancelation System for Python Streams

A comprehensive, production-ready cancelation system for async operations
with support for timeouts, signals, conditions, and manual cancelation.
"""

from .core.cancelable import Cancelable, current_operation
from .core.exceptions import (
    CancelationError,
    ConditionCancelation,
    ManualCancelation,
    ParentCancelation,
    SignalCancelation,
    TimeoutCancelation,
)
from .core.models import CancelationReason, OperationContext, OperationStatus
from .core.registry import OperationRegistry
from .core.token import CancelationToken
from .types import (
    ErrorCallback,
    ErrorCallbackType,
    ProgressCallback,
    ProgressCallbackType,
    StatusCallback,
    StatusCallbackType,
    ensure_cancelable,
)
from .utils.anyio_bridge import AnyioBridge, call_soon_threadsafe
from .utils.threading_bridge import ThreadSafeRegistry
import importlib.metadata

from .utils.decorators import (
    cancelable,
    cancelable_combine,
    cancelable_with_condition,
    cancelable_with_signal,
    cancelable_with_token,
    with_cancelable,
    with_timeout,
)
from .utils.streams import cancelable_stream
from .sources.composite import AllOfSource, AnyOfSource, CompositeSource

try:
    __version__ = importlib.metadata.version("hother-cancelable")
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0+dev"

__all__ = [
    # Models
    "OperationStatus",
    "CancelationReason",
    "OperationContext",
    "CancelationToken",
    # Core
    "Cancelable",
    "OperationRegistry",
    "ThreadSafeRegistry",
    "current_operation",
    # Exceptions
    "CancelationError",
    "TimeoutCancelation",
    "ManualCancelation",
    "SignalCancelation",
    "ConditionCancelation",
    "ParentCancelation",
    # Sources
    "CompositeSource",
    "AnyOfSource",
    "AllOfSource",
    # Types
    "ProgressCallback",
    "ProgressCallbackType",
    "StatusCallback",
    "StatusCallbackType",
    "ErrorCallback",
    "ErrorCallbackType",
    "ensure_cancelable",
    # Utilities
    "cancelable",
    "cancelable_with_token",
    "cancelable_with_signal",
    "cancelable_with_condition",
    "cancelable_combine",
    "with_cancelable",
    "with_timeout",
    "cancelable_stream",
    "AnyioBridge",
    "call_soon_threadsafe",
]
