"""Retry mechanism with exponential backoff for tool calls."""
import asyncio
import logging
from functools import wraps
from typing import Callable, Awaitable

logger = logging.getLogger(__name__)

# Exceptions that should trigger retry
RETRYABLE_EXCEPTIONS = (ConnectionError, TimeoutError, OSError)


def retry_on_failure(
    max_retries: int = 3,
    backoff: float = 2.0,
    initial_delay: float = 1.0,
    retryable_exceptions: tuple = RETRYABLE_EXCEPTIONS,
):
    """Decorator that retries a function on failure with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts
        backoff: Exponential backoff multiplier
        initial_delay: Initial delay in seconds before first retry
        retryable_exceptions: Exception types that trigger retry
    """

    def decorator(func: Callable[..., Awaitable]):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        delay = initial_delay * (backoff**attempt)
                        logger.warning(
                            f"Retry {attempt + 1}/{max_retries} for {func.__name__}: "
                            f"{e}. Waiting {delay:.1f}s..."
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            f"All {max_retries} retries failed for {func.__name__}: {e}"
                        )
                except Exception as e:
                    # Non-retryable exception, fail immediately
                    logger.error(f"Non-retryable error in {func.__name__}: {e}")
                    raise
            raise last_exception

        return wrapper

    return decorator