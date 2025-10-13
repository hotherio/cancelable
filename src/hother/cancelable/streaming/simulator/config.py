"""Configuration models for stream simulation."""


from pydantic import BaseModel, Field, model_validator


class StreamConfig(BaseModel):
    """Configuration for stream simulation."""

    chunk_size: int = Field(default=1, ge=1, description="Base chunk size")
    base_delay: float = Field(default=0.05, ge=0, description="Base delay between chunks")
    jitter: float = Field(default=0.02, ge=0, description="Maximum jitter amount")
    jitter_probability: float = Field(default=0.3, ge=0, le=1, description="Probability of applying jitter")
    burst_probability: float = Field(default=0.1, ge=0, le=1, description="Chance of sending multiple chunks quickly")
    burst_size: int = Field(default=3, ge=1, description="Number of chunks in a burst")
    stall_probability: float = Field(default=0.05, ge=0, le=1, description="Chance of longer delay (network stall)")
    stall_duration: float = Field(default=0.5, ge=0, description="Duration of network stalls")
    variable_chunk_size: bool = Field(default=False, description="Enable variable chunk sizes")
    chunk_size_range: tuple[int, int] | None = Field(default=None, description="(min, max) range for chunk sizes")
    chunk_size_weights: list[float] | None = Field(default=None, description="Weights for different chunk sizes")

    @model_validator(mode="after")
    def set_default_chunk_size_range(self):
        """Set default values for chunk size range if variable_chunk_size is enabled."""
        if self.variable_chunk_size and self.chunk_size_range is None:
            min_size = max(1, self.chunk_size // 2)
            max_size = self.chunk_size * 2
            self.chunk_size_range = (min_size, max_size)

        if self.chunk_size_range is not None:
            min_size, max_size = self.chunk_size_range
            if min_size < 1:
                raise ValueError("Minimum chunk size must be at least 1")
            if min_size > max_size:
                raise ValueError("Minimum chunk size cannot be greater than maximum chunk size")

        return self
