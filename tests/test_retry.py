"""Tests for app.retry module - retry_on_failure decorator."""
import asyncio
import pytest


class TestRetryOnFailure:
    """Tests for retry_on_failure decorator."""

    def test_decorator_imports(self):
        """retry_on_failure should be importable."""
        from app.retry import retry_on_failure
        assert callable(retry_on_failure)

    @pytest.mark.asyncio
    async def test_success_no_retry(self):
        """Successful call should not retry."""
        from app.retry import retry_on_failure

        call_count = 0

        @retry_on_failure(max_retries=3, backoff=2.0, initial_delay=0.01)
        async def succeed():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await succeed()
        assert result == "ok"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retry_on_connection_error(self):
        """ConnectionError should trigger retry, eventually succeed."""
        from app.retry import retry_on_failure

        call_count = 0

        @retry_on_failure(max_retries=3, backoff=2.0, initial_delay=0.01)
        async def fail_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("temporary failure")
            return "recovered"

        result = await fail_then_succeed()
        assert result == "recovered"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_retry_exhausted(self):
        """After max_retries, the last exception should be raised."""
        from app.retry import retry_on_failure

        call_count = 0

        @retry_on_failure(max_retries=2, backoff=2.0, initial_delay=0.01)
        async def always_fail():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("persistent failure")

        with pytest.raises(ConnectionError, match="persistent failure"):
            await always_fail()
        assert call_count == 3  # 1 initial + 2 retries

    @pytest.mark.asyncio
    async def test_non_retryable_fails_immediately(self):
        """Non-retryable exceptions should fail immediately without retry."""
        from app.retry import retry_on_failure

        call_count = 0

        @retry_on_failure(max_retries=3, backoff=2.0, initial_delay=0.01)
        async def fail_value_error():
            nonlocal call_count
            call_count += 1
            raise ValueError("not retryable")

        with pytest.raises(ValueError, match="not retryable"):
            await fail_value_error()
        assert call_count == 1  # No retry

    @pytest.mark.asyncio
    async def test_retry_with_timeout_error(self):
        """TimeoutError should trigger retry."""
        from app.retry import retry_on_failure

        call_count = 0

        @retry_on_failure(max_retries=2, backoff=1.0, initial_delay=0.01)
        async def fail_timeout():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise TimeoutError("timed out")
            return "ok"

        result = await fail_timeout()
        assert result == "ok"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_exponential_backoff_delays(self):
        """Retry delays should increase exponentially."""
        from app.retry import retry_on_failure
        import time

        call_count = 0
        delays = []

        @retry_on_failure(max_retries=2, backoff=2.0, initial_delay=0.05)
        async def failing_with_timing():
            nonlocal call_count
            delays.append(time.monotonic())
            call_count += 1
            raise ConnectionError("fail")

        with pytest.raises(ConnectionError):
            await failing_with_timing()

        # 3 calls: initial, retry1, retry2
        assert len(delays) == 3
        # Check increasing delays
        d1 = delays[1] - delays[0]
        d2 = delays[2] - delays[1]
        assert d2 > d1 * 0.5  # Should be roughly 2x

    @pytest.mark.asyncio
    async def test_custom_retryable_exceptions(self):
        """Should accept custom retryable exception types."""
        from app.retry import retry_on_failure

        class CustomRetryableError(Exception):
            pass

        call_count = 0

        @retry_on_failure(
            max_retries=2, backoff=1.0, initial_delay=0.01,
            retryable_exceptions=(CustomRetryableError,),
        )
        async def custom_fail():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise CustomRetryableError("custom")
            return "ok"

        result = await custom_fail()
        assert result == "ok"
        assert call_count == 3
