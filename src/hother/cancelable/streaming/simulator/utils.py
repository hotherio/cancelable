"""Utility functions for stream simulation."""

import random

from .config import StreamConfig


def get_random_chunk_size(config: StreamConfig) -> int:
    """Get a random chunk size based on configuration."""
    if not config.variable_chunk_size:
        return config.chunk_size

    if config.chunk_size_range is None:
        raise RuntimeError("No chunk size range provided with variable_chunk_size")

    min_size, max_size = config.chunk_size_range

    if config.chunk_size_weights:
        sizes = list(range(min_size, max_size + 1))
        weights = config.chunk_size_weights[: len(sizes)]
        if len(weights) < len(sizes):
            weights.extend([1] * (len(sizes) - len(weights)))
        return random.choices(sizes, weights=weights)[0]
    return random.randint(min_size, max_size)
