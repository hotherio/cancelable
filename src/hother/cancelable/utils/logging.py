"""
Logging utilities for the cancelable library.
"""

import logging
import sys
from typing import Optional

import structlog


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    Get a standard library logger instance.

    Args:
        name: Logger name. If None, uses the calling module's name

    Returns:
        A configured standard library logger
    """
    if name is None:
        import inspect
        frame = inspect.currentframe()
        if frame and frame.f_back:
            name = frame.f_back.f_globals.get('__name__', 'cancelable')
        else:
            name = 'cancelable'

    return logging.getLogger(name)


def configure_logging(
    log_level: str = "INFO",
    json_output: bool = False,
    dev_mode: bool = True
) -> None:
    """
    Configure standard library logging for the library.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        json_output: Whether to output JSON format
        dev_mode: Whether to use dev-friendly console output
    """
    # Configure structlog to enable **kwargs logging
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure standard logging
    if json_output:
        # JSON format for production
        formatter = logging.Formatter(
            '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "name": "%(name)s", "message": "%(message)s"}'
        )
    elif dev_mode:
        # Human-readable format for development
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
    else:
        # Simple format
        formatter = logging.Formatter(
            "%(levelname)s - %(name)s - %(message)s"
        )

    # Setup handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))
    root_logger.addHandler(handler)

    # Prevent duplicate handlers if called multiple times
    root_logger.propagate = False
