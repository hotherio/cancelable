"""
Unit tests for logging.py utilities.
"""

import logging
from unittest.mock import patch

from hother.cancelable.utils.logging import get_logger


class TestGetLogger:
    """Test get_logger function."""

    def test_get_logger_with_name(self):
        """Test getting logger with explicit name."""
        logger = get_logger("test_logger")
        assert isinstance(logger, logging.Logger)
        assert logger.name == "test_logger"

    def test_get_logger_without_name(self):
        """Test getting logger without name (uses caller module)."""
        # Mock inspect to control the frame
        with patch('inspect.currentframe') as mock_frame:
            mock_frame.return_value = None
            logger = get_logger()
            assert isinstance(logger, logging.Logger)
            assert logger.name == "cancelable"

    def test_get_logger_with_frame(self):
        """Test getting logger with frame inspection."""
        # Mock inspect to return a frame with __name__
        mock_frame = type('Frame', (), {
            'f_back': type('Frame', (), {
                'f_globals': {'__name__': 'test_module'}
            })()
        })()

        with patch('inspect.currentframe', return_value=mock_frame):
            logger = get_logger()
            assert logger.name == "test_module"

    def test_get_logger_returns_same_instance(self):
        """Test that get_logger returns the same logger instance for the same name."""
        logger1 = get_logger("test_logger")
        logger2 = get_logger("test_logger")
        assert logger1 is logger2

    def test_get_logger_hierarchy(self):
        """Test that loggers follow proper hierarchy."""
        parent_logger = get_logger("hother.cancelable")
        child_logger = get_logger("hother.cancelable.core")

        assert child_logger.parent == parent_logger or child_logger.parent == parent_logger.parent

    def test_null_handler_present(self):
        """Test that NullHandler is added to prevent 'No handler found' warnings."""
        logger = logging.getLogger("hother.cancelable")

        # Check that at least one NullHandler exists
        null_handlers = [h for h in logger.handlers if isinstance(h, logging.NullHandler)]
        assert len(null_handlers) > 0