"""
YAML Plugin System Logging

Provides centralized logging configuration for the YAML plugin system.
"""

import logging
from typing import Optional

# Module logger
logger = logging.getLogger("yaml_plugin")

# Default format
DEFAULT_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def configure_logging(
    level: int = logging.WARNING,
    format_str: Optional[str] = None,
    date_format: Optional[str] = None,
):
    """
    Configure the YAML plugin system logging.

    Args:
        level: Logging level (e.g., logging.DEBUG, logging.INFO)
        format_str: Log message format string
        date_format: Date format string
    """
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            format_str or DEFAULT_FORMAT,
            datefmt=date_format or DEFAULT_DATE_FORMAT,
        )
    )

    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False


def set_debug_enabled(enabled: bool):
    """
    Enable or disable debug logging.

    Args:
        enabled: True to enable debug logging, False for warning-only
    """
    level = logging.DEBUG if enabled else logging.WARNING
    logger.setLevel(level)


def is_debug_enabled() -> bool:
    """Check if debug logging is enabled."""
    return logger.level <= logging.DEBUG


# Initialize with default configuration (warnings only)
configure_logging()
