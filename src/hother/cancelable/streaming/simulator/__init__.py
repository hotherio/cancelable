"""Block extraction system."""

from .config import StreamConfig
from .simulator import simulate_stream
from .utils import get_random_chunk_size

__all__ = [
    "StreamConfig",
    "simulate_stream",
    "get_random_chunk_size"
]
