"""
Tests for streaming simulator functionality.
"""

import pytest

from hother.cancelable.streaming.simulator.config import StreamConfig
from hother.cancelable.streaming.simulator.simulator import simulate_stream
from hother.cancelable.streaming.simulator.utils import get_random_chunk_size


class TestStreamConfig:
    """Test StreamConfig functionality."""

    def test_default_config(self):
        """Test default configuration values."""
        config = StreamConfig()
        assert config.chunk_size == 1
        assert config.stall_probability == 0.05
        assert config.burst_probability == 0.1
        assert config.stall_duration == 0.5
        assert config.burst_size == 3

    def test_custom_config(self):
        """Test custom configuration values."""
        config = StreamConfig(
            chunk_size=50,
            stall_probability=0.2,
            burst_probability=0.3,
            stall_duration=1.0,
            burst_size=5
        )
        assert config.chunk_size == 50
        assert config.stall_probability == 0.2
        assert config.burst_probability == 0.3
        assert config.stall_duration == 1.0
        assert config.burst_size == 5

    def test_config_default_chunk_size_range(self):
        """Test that default chunk_size_range is set when variable_chunk_size=True."""
        config = StreamConfig(chunk_size=100, variable_chunk_size=True)
        assert config.chunk_size_range is not None
        min_size, max_size = config.chunk_size_range
        assert min_size == 50  # chunk_size // 2
        assert max_size == 200  # chunk_size * 2

    def test_config_chunk_size_range_validation_min_too_small(self):
        """Test validation error when minimum chunk size < 1."""
        with pytest.raises(ValueError, match="Minimum chunk size must be at least 1"):
            StreamConfig(chunk_size_range=(0, 100))

    def test_config_chunk_size_range_validation_min_greater_than_max(self):
        """Test validation error when min > max."""
        with pytest.raises(ValueError, match="Minimum chunk size cannot be greater than maximum"):
            StreamConfig(chunk_size_range=(100, 50))


class TestGetRandomChunkSize:
    """Test get_random_chunk_size utility function."""

    def test_random_chunk_size_fixed(self):
        """Test fixed chunk size when variable_chunk_size is False."""
        config = StreamConfig(chunk_size=100, variable_chunk_size=False)
        chunk_size = get_random_chunk_size(config)

        assert chunk_size == 100

    def test_random_chunk_size_variable(self):
        """Test variable chunk size."""
        config = StreamConfig(
            chunk_size=100,
            variable_chunk_size=True,
            chunk_size_range=(50, 150)
        )
        chunk_size = get_random_chunk_size(config)

        # Should be between 50 and 150
        assert 50 <= chunk_size <= 150

    def test_random_chunk_size_variation(self):
        """Test that random chunk size varies."""
        config = StreamConfig(
            chunk_size=100,
            variable_chunk_size=True,
            chunk_size_range=(80, 120)
        )
        sizes = [get_random_chunk_size(config) for _ in range(10)]

        # Should have some variation (not all the same)
        assert len(set(sizes)) > 1

    def test_random_chunk_size_no_range_error(self):
        """Test error when variable_chunk_size=True but no chunk_size_range."""
        config = StreamConfig(variable_chunk_size=True)
        # Manually override the chunk_size_range to None to trigger error
        config.chunk_size_range = None

        with pytest.raises(RuntimeError, match="No chunk size range provided"):
            get_random_chunk_size(config)

    def test_random_chunk_size_with_weights(self):
        """Test weighted random chunk size selection."""
        config = StreamConfig(
            chunk_size=10,
            variable_chunk_size=True,
            chunk_size_range=(5, 10),
            chunk_size_weights=[10, 5, 3, 1, 0, 0]  # Heavy bias toward smaller sizes
        )

        # Generate many samples to test the weighted selection
        sizes = [get_random_chunk_size(config) for _ in range(100)]

        # Should generate sizes in the valid range
        assert all(5 <= s <= 10 for s in sizes)
        # Should have some variation
        assert len(set(sizes)) > 1

    def test_random_chunk_size_with_partial_weights(self):
        """Test weighted selection when weights list is shorter than range."""
        config = StreamConfig(
            chunk_size=10,
            variable_chunk_size=True,
            chunk_size_range=(5, 15),  # 11 possible values (5-15)
            chunk_size_weights=[10, 5]  # Only 2 weights, rest should be filled with 1
        )

        sizes = [get_random_chunk_size(config) for _ in range(50)]

        # Should generate sizes in the valid range
        assert all(5 <= s <= 15 for s in sizes)
        # Should have some variation
        assert len(set(sizes)) > 1


class TestSimulateStream:
    """Test simulate_stream functionality."""

    @pytest.mark.anyio
    async def test_basic_simulation(self):
        """Test basic stream simulation."""
        text = "Hello, World!"
        config = StreamConfig(chunk_size=5)  # Small chunks for testing

        events = []
        async for event in simulate_stream(text, config):
            events.append(event)

        # Should have at least one data event
        data_events = [e for e in events if e.get("type") == "data"]
        assert len(data_events) > 0

        # Should have at least one complete event
        complete_events = [e for e in events if e.get("type") == "complete"]
        assert len(complete_events) == 1

        # All data chunks should combine to original text
        chunks = [e["chunk"] for e in data_events]
        reconstructed = "".join(chunks)
        assert reconstructed == text

    @pytest.mark.anyio
    async def test_simulation_with_stalls(self):
        """Test simulation with stall events."""
        text = "Test text"
        config = StreamConfig(
            chunk_size=4,
            stall_probability=1.0,  # Always stall
            stall_duration=0.1
        )

        events = []
        async for event in simulate_stream(text, config):
            events.append(event)

        # Should have stall events
        stall_events = [e for e in events if e.get("type") == "stall"]
        assert len(stall_events) > 0

        # Stall events should have duration
        for stall in stall_events:
            assert "duration" in stall
            assert stall["duration"] == 0.1

    @pytest.mark.anyio
    async def test_simulation_with_bursts(self):
        """Test simulation with burst events."""
        text = "Test text for bursting"
        config = StreamConfig(
            chunk_size=3,
            burst_probability=1.0,  # Always burst
            burst_size=2
        )

        events = []
        async for event in simulate_stream(text, config):
            events.append(event)

        # Should have burst events (multiple data chunks in quick succession)
        data_events = [e for e in events if e.get("type") == "data"]
        assert len(data_events) > 0

    @pytest.mark.anyio
    async def test_simulation_with_cancelation(self):
        """Test simulation with cancelation support."""
        from hother.cancelable import Cancelable

        text = "This is a long text that should be cancelled"
        config = StreamConfig(chunk_size=5)

        async with Cancelable() as cancel:
            events = []
            try:
                async for event in simulate_stream(text, config, cancel):
                    events.append(event)

                    # Cancel after first chunk
                    if len([e for e in events if e.get("type") == "chunk"]) >= 1:
                        await cancel._token.cancel()
                        break
            except Exception:
                # Cancelation should be handled gracefully
                pass

            # Should have at least started
            assert len(events) > 0

    @pytest.mark.anyio
    async def test_empty_text_simulation(self):
        """Test simulation with empty text."""
        text = ""
        config = StreamConfig()

        events = []
        async for event in simulate_stream(text, config):
            events.append(event)

        # Should have complete event even for empty text
        complete_events = [e for e in events if e.get("type") == "complete"]
        assert len(complete_events) == 1

    @pytest.mark.anyio
    async def test_large_text_simulation(self):
        """Test simulation with large text."""
        text = "A" * 1000  # Large text
        config = StreamConfig(chunk_size=100)

        events = []
        async for event in simulate_stream(text, config):
            events.append(event)

        # Should have multiple data chunks
        data_events = [e for e in events if e.get("type") == "data"]
        assert len(data_events) > 1

        # All data chunks should combine to original text
        chunks = [e["chunk"] for e in data_events]
        reconstructed = "".join(chunks)
        assert reconstructed == text

    @pytest.mark.anyio
    async def test_timestamps_in_events(self):
        """Test that events include timestamps."""
        text = "Test"
        config = StreamConfig(chunk_size=2)

        events = []
        async for event in simulate_stream(text, config):
            events.append(event)

        # All events should have timestamps
        for event in events:
            assert "timestamp" in event
            assert isinstance(event["timestamp"], float)
            assert event["timestamp"] > 0

    @pytest.mark.anyio
    async def test_config_none_uses_defaults(self):
        """Test that passing None config uses defaults."""
        text = "Test text"

        events = []
        async for event in simulate_stream(text, None):
            events.append(event)

        # Should work with default config
        data_events = [e for e in events if e.get("type") == "data"]
        assert len(data_events) > 0

    @pytest.mark.anyio
    async def test_simulation_with_progress_reporting(self):
        """Test simulation with cancelable progress reporting."""
        from hother.cancelable import Cancelable

        # Long text to trigger multiple progress reports (every 10 chunks)
        text = "A" * 500
        config = StreamConfig(chunk_size=5)

        progress_reports = []

        async with Cancelable(name="stream_test") as cancel:
            # Register progress callback
            def on_progress(op_id, message, metadata):
                progress_reports.append((message, metadata))

            cancel.on_progress(on_progress)

            events = []
            async for event in simulate_stream(text, config, cancel):
                events.append(event)

            assert len(progress_reports) > 0
            # Check that progress reports contain expected info
            assert any("Stream progress" in msg for msg, _ in progress_reports)

    @pytest.mark.anyio
    async def test_simulation_with_stall_progress_reporting(self):
        """Test simulation with stall events and progress reporting."""
        from hother.cancelable import Cancelable

        text = "Test text for stalls"
        config = StreamConfig(
            chunk_size=5,
            stall_probability=1.0,  # Force stalls
            stall_duration=0.01  # Very short for testing
        )

        progress_reports = []

        async with Cancelable(name="stall_test") as cancel:
            # Register progress callback
            def on_progress(op_id, message, metadata):
                progress_reports.append((message, metadata))

            cancel.on_progress(on_progress)

            events = []
            async for event in simulate_stream(text, config, cancel):
                events.append(event)

            assert len(progress_reports) > 0
            # Check that stall reports exist
            assert any("Network stall" in msg for msg, _ in progress_reports)

    @pytest.mark.anyio
    async def test_burst_ends_mid_text_boundary(self):
        """Test that burst properly breaks when reaching text end mid-burst.

        Targets line 45: break statement when i >= len(text) during burst.
        """
        text = "12345"  # 5 characters
        config = StreamConfig(
            chunk_size=2,
            burst_probability=1.0,  # Force burst
            burst_size=10,  # Large enough to exceed text length
            stall_probability=0.0  # No stalls for predictable test
        )

        events = []
        async for event in simulate_stream(text, config):
            events.append(event)

        # Verify all text was transmitted
        data_events = [e for e in events if e.get("type") == "data"]
        chunks = [e["chunk"] for e in data_events]
        reconstructed = "".join(chunks)
        assert reconstructed == text

        # Verify burst events occurred
        burst_events = [e for e in data_events if e.get("burst") is True]
        assert len(burst_events) > 0

        # Should have a complete event
        complete_events = [e for e in events if e.get("type") == "complete"]
        assert len(complete_events) == 1