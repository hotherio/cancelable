"""Tests for block models."""

import pytest
from pydantic import ValidationError

from cancelable.streaming.blocks.models import BlockExtractionState, BlockExtractionStatus, ExtractedBlock


class TestExtractedBlock:
    """Test ExtractedBlock model."""

    def test_valid_block(self):
        """Test creating a valid block."""
        block = ExtractedBlock(hash_id="abc123", block_type="simple", parameters={"key": "value"}, content="test content", raw_content="test content")
        assert block.hash_id == "abc123"
        assert block.block_type == "simple"
        assert block.parameters == {"key": "value"}

    def test_log_context(self):
        """Test log context generation."""
        block = ExtractedBlock(hash_id="test01", block_type="action", parameters={"name": "test"}, content={"action": "test"}, raw_content="test content")
        context = block.log_context()
        assert context["block_id"] == "test01"
        assert context["block_type"] == "action"
        assert context["content_length"] == 12
        assert context["has_parameters"] is True


class TestBlockExtractionState:
    """Test BlockExtractionState model."""

    def test_initial_state(self):
        """Test initial state."""
        state = BlockExtractionState()
        assert state.status == BlockExtractionStatus.COMPLETED
        assert state.current_state_description == "scanning_for_blocks"
        assert state.processed_lines == 0
        assert state.extracted_blocks == []

    def test_in_block_state(self):
        """Test state when processing a block."""
        state = BlockExtractionState(current_block_hash="test01", current_block_header="action:test", current_block_lines=["line1", "line2"], processed_lines=10)
        assert state.status == BlockExtractionStatus.IN_BLOCK
        assert "in_block_test01_2_lines" in state.current_state_description

    def test_reset_current_block(self):
        """Test resetting current block."""
        state = BlockExtractionState(current_block_hash="test01", current_block_header="action:test", current_block_lines=["line1", "line2"])
        state.reset_current_block()
        assert state.current_block_hash is None
        assert state.current_block_header is None
        assert state.current_block_lines == []
