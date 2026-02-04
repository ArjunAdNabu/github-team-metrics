"""Utility functions for GitHub Team Metrics project."""

import logging
import time
import sys
from datetime import datetime, timedelta
from typing import Callable, Any, Tuple
from functools import wraps
import re


def setup_logging(log_level: str = 'INFO') -> logging.Logger:
    """
    Configure logging with consistent format.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)

    Returns:
        Logger instance
    """
    # Create logger
    logger = logging.getLogger('github_metrics')
    logger.setLevel(getattr(logging, log_level.upper()))

    # Remove existing handlers
    logger.handlers = []

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, log_level.upper()))

    # Formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(formatter)

    logger.addHandler(console_handler)

    return logger


def retry_with_exponential_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exceptions: tuple = (Exception,)
):
    """
    Decorator that retries a function with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        exceptions: Tuple of exceptions to catch

    Returns:
        Decorated function
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            retries = 0
            delay = base_delay

            while retries <= max_retries:
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    retries += 1
                    if retries > max_retries:
                        raise

                    logger = logging.getLogger('github_metrics')
                    logger.warning(
                        f"{func.__name__} failed (attempt {retries}/{max_retries}): {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )

                    time.sleep(delay)
                    delay = min(delay * 2, max_delay)

            return None
        return wrapper
    return decorator


def calculate_date_range(
    days_back: int = 30,
    start_date: str = None,
    end_date: str = None
) -> Tuple[str, str]:
    """
    Calculate date range for metrics collection.

    Args:
        days_back: Number of days to look back (default: 30)
        start_date: Optional start date in YYYY-MM-DD format
        end_date: Optional end date in YYYY-MM-DD format

    Returns:
        Tuple of (start_date, end_date) in ISO format with timezone
    """
    from datetime import timezone

    if start_date and end_date:
        # Use provided dates
        start = datetime.fromisoformat(start_date)
        end = datetime.fromisoformat(end_date)
    else:
        # Calculate from days_back (timezone-aware)
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days_back)

    # Ensure timezone-aware
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)

    return start.isoformat(), end.isoformat()


def validate_date_range(start_date: str, end_date: str) -> bool:
    """
    Validate date range.

    Args:
        start_date: Start date in ISO format
        end_date: End date in ISO format

    Returns:
        True if valid, raises ValueError otherwise
    """
    try:
        start = datetime.fromisoformat(start_date)
        end = datetime.fromisoformat(end_date)

        if start >= end:
            raise ValueError(f"Start date must be before end date: {start_date} >= {end_date}")

        return True
    except (ValueError, TypeError) as e:
        raise ValueError(f"Invalid date format: {e}")


def sanitize_filename(filename: str) -> str:
    """
    Remove invalid characters from filename.

    Args:
        filename: Original filename

    Returns:
        Sanitized filename safe for filesystem
    """
    # Remove invalid characters
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)

    # Replace spaces with underscores
    filename = filename.replace(' ', '_')

    # Remove multiple underscores
    filename = re.sub(r'_+', '_', filename)

    return filename


def format_duration(seconds: float) -> str:
    """
    Format duration in human-readable format.

    Args:
        seconds: Duration in seconds

    Returns:
        Formatted string (e.g., "2m 30s", "1h 15m")
    """
    if seconds < 60:
        return f"{seconds:.0f}s"

    minutes = seconds / 60
    if minutes < 60:
        return f"{minutes:.1f}m"

    hours = minutes / 60
    if hours < 24:
        return f"{hours:.1f}h"

    days = hours / 24
    return f"{days:.1f}d"


def calculate_rate_limit_sleep(reset_timestamp: int) -> float:
    """
    Calculate sleep time until rate limit resets.

    Args:
        reset_timestamp: Unix timestamp when rate limit resets

    Returns:
        Sleep time in seconds
    """
    now = datetime.now().timestamp()
    sleep_time = max(0, reset_timestamp - now)
    return sleep_time


def generate_output_filename(start_date: str, end_date: str) -> str:
    """
    Generate output filename with timestamp.

    Args:
        start_date: Start date in ISO format
        end_date: End date in ISO format

    Returns:
        Filename like "team_metrics_20250115_100033.xlsx"
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"team_metrics_{timestamp}.xlsx"


class ProgressTracker:
    """Track and display progress for long-running operations."""

    def __init__(self, total: int, description: str):
        """
        Initialize progress tracker.

        Args:
            total: Total number of items to process
            description: Description of the operation
        """
        self.total = total
        self.current = 0
        self.description = description
        self.start_time = time.time()
        self.logger = logging.getLogger('github_metrics')

    def update(self, increment: int = 1):
        """
        Update progress.

        Args:
            increment: Number of items processed
        """
        self.current += increment
        percentage = (self.current / self.total) * 100 if self.total > 0 else 0
        elapsed = time.time() - self.start_time

        self.logger.info(
            f"{self.description}: {self.current}/{self.total} "
            f"({percentage:.1f}%) - {format_duration(elapsed)} elapsed"
        )

    def finish(self):
        """Mark progress as complete."""
        elapsed = time.time() - self.start_time
        self.logger.info(
            f"{self.description}: Complete! "
            f"Processed {self.current}/{self.total} in {format_duration(elapsed)}"
        )


def parse_github_datetime(dt_str: str) -> datetime:
    """
    Parse GitHub API datetime string.

    Args:
        dt_str: Datetime string from GitHub API (ISO format)

    Returns:
        Parsed datetime object
    """
    return datetime.fromisoformat(dt_str.replace('Z', '+00:00'))


def calculate_hours_between(start: str, end: str) -> float:
    """
    Calculate hours between two datetime strings.

    Args:
        start: Start datetime (ISO format or parseable string)
        end: End datetime (ISO format or parseable string)

    Returns:
        Hours between the two datetimes
    """
    try:
        # Handle GitHub's 'Z' timezone suffix
        if isinstance(start, str):
            start_dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
        else:
            start_dt = start

        if isinstance(end, str):
            end_dt = datetime.fromisoformat(end.replace('Z', '+00:00'))
        else:
            end_dt = end

        delta = end_dt - start_dt
        return delta.total_seconds() / 3600
    except (ValueError, TypeError):
        return 0.0
