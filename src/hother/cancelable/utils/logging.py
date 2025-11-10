"""
Logging utilities for the cancelable library.

Following Python library best practices, this module provides logger access
but does not configure logging. Applications using cancelable should configure
their own logging as needed.
"""

import logging
from typing import Optional


# Add a NullHandler to prevent "No handler found" warnings
logging.getLogger("hother.cancelable").addHandler(logging.NullHandler())


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    Get a standard library logger instance.

    Args:
        name: Logger name. If None, uses the calling module's name

    Returns:
        A configured standard library logger

    Note:
        This function does not configure logging handlers or formatters.
        Applications should configure logging using logging.basicConfig()
        or their preferred logging configuration method.

    Example:
        In your application code:
        ```python
        import logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

        from hother.cancelable.utils.logging import get_logger
        logger = get_logger(__name__)
        logger.info("Application started")
        ```
    """
    if name is None:
        import inspect

        frame = inspect.currentframe()
        if frame and frame.f_back:
            name = frame.f_back.f_globals.get("__name__", "cancelable")
        else:
            name = "cancelable"

    return logging.getLogger(name)
