"""
Logging configuration for BridgeOS.

Usage in any module:
    import logging
    logger = logging.getLogger(__name__)
    logger.info("Something happened")

Call setup_logging() once at application startup (in bot.py).
"""
import logging
import sys


def setup_logging(level: str = "INFO"):
    """
    Configure logging for the entire application.
    Call once at startup before any logger is used.

    Args:
        level: Log level string — "DEBUG", "INFO", "WARNING", "ERROR"
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler (stdout so Railway/Docker captures it)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    # Root logger
    root = logging.getLogger()
    root.setLevel(log_level)

    # Avoid duplicate handlers on repeated calls
    if not root.handlers:
        root.addHandler(handler)

    # Quiet noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("telegram.ext").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)

    logging.getLogger(__name__).info(f"Logging initialized at {level} level")
