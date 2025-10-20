"""
Condition-based cancellation source implementation.
"""

import inspect
from collections.abc import Awaitable, Callable

import anyio

from hother.cancelable.core.models import CancellationReason
from hother.cancelable.sources.base import CancellationSource
from hother.cancelable.utils.logging import get_logger

logger = get_logger(__name__)


class ConditionSource(CancellationSource):
    """
    Cancellation source that monitors a condition function.

    Cancels when the condition function returns True.
    """

    def __init__(
        self,
        condition: Callable[[], bool | Awaitable[bool]],
        check_interval: float = 0.1,
        condition_name: str | None = None,
        name: str | None = None,
    ):
        """
        Initialize condition source.

        Args:
            condition: Function that returns True when cancellation should occur
            check_interval: How often to check condition (seconds)
            condition_name: Name for the condition (for logging)
            name: Optional name for the source
        """
        super().__init__(CancellationReason.CONDITION, name)

        self.condition = condition
        self.check_interval = check_interval
        self.condition_name = condition_name or getattr(condition, "__name__", "condition")
        self.triggered = False
        self._task_group: anyio.abc.TaskGroup | None = None

        # Validate check interval
        if check_interval <= 0:
            raise ValueError(f"Check interval must be positive, got {check_interval}")

        # Determine if condition is async
        self._is_async = inspect.iscoroutinefunction(condition)

    async def start_monitoring(self, scope: anyio.CancelScope) -> None:
        """
        Start monitoring the condition.

        Args:
            scope: Cancel scope to trigger when condition is met
        """
        self.scope = scope

        # Create task group for background monitoring
        self._task_group = anyio.create_task_group()
        await self._task_group.__aenter__()

        # Start monitoring task
        self._task_group.start_soon(self._monitor_condition)

        logger.debug(
            "Condition source activated",
            extra={
                "source": self.name,
                "condition_name": self.condition_name,
                "check_interval": self.check_interval,
            },
        )

    async def stop_monitoring(self) -> None:
        """Stop monitoring the condition."""
        if self._task_group:
            # Cancel all tasks in the group
            self._task_group.cancel_scope.cancel()

            # Try to properly exit the task group, but shield from cancellation
            # and handle errors if we're in a different context
            try:
                with anyio.CancelScope(shield=True):
                    await self._task_group.__aexit__(None, None, None)
            except (anyio.get_cancelled_exc_class(), RuntimeError, Exception) as e:
                # Task group exit failed, likely due to context mismatch
                # This is acceptable as the cancel scope was already cancelled
                logger.debug(f"Task group cleanup skipped: {type(e).__name__}")
            finally:
                self._task_group = None

        logger.debug(
            "Condition source stopped",
            extra={
                "source": self.name,
                "condition_name": self.condition_name,
                "triggered": self.triggered,
            },
        )

    async def _monitor_condition(self) -> None:
        """Monitor the condition in a loop."""
        check_count = 0

        try:
            while not self.triggered:
                check_count += 1
                logger.debug(f"Condition check #{check_count} for {self.condition_name}")

                # Check condition
                try:
                    if self._is_async:
                        result = await self.condition()
                    else:
                        # Run sync condition in thread pool
                        result = await anyio.to_thread.run_sync(self.condition)

                    logger.debug(f"Condition check #{check_count} returned: {result}")

                    if result:
                        self.triggered = True
                        logger.debug(f"Condition '{self.condition_name}' met after {check_count} checks")

                        # Trigger cancellation through the base class method
                        await self.trigger_cancellation(f"Condition '{self.condition_name}' met after {check_count} checks")
                        break

                except Exception as e:
                    logger.error(
                        "Error checking condition",
                        extra={
                            "source": self.name,
                            "condition_name": self.condition_name,
                            "error": str(e),
                        },
                        exc_info=True,
                    )
                    # Continue monitoring despite errors

                # Wait before next check
                await anyio.sleep(self.check_interval)

        except anyio.get_cancelled_exc_class():
            # Task was cancelled
            logger.debug("Condition monitoring task cancelled")
            raise
        except Exception as e:
            logger.error(
                "Unexpected error in condition monitor",
                extra={
                    "source": self.name,
                    "error": str(e),
                },
                exc_info=True,
            )


class ResourceConditionSource(ConditionSource):
    """
    Specialized condition source for monitoring system resources.

    Useful for cancelling operations when resources are constrained.
    """

    def __init__(
        self,
        memory_threshold: float | None = None,
        cpu_threshold: float | None = None,
        disk_threshold: float | None = None,
        check_interval: float = 5.0,
        name: str | None = None,
    ):
        """
        Initialize resource condition source.

        Args:
            memory_threshold: Cancel if memory usage exceeds this percentage
            cpu_threshold: Cancel if CPU usage exceeds this percentage
            disk_threshold: Cancel if disk usage exceeds this percentage
            check_interval: How often to check resources (seconds)
            name: Optional name for the source
        """
        self.memory_threshold = memory_threshold
        self.cpu_threshold = cpu_threshold
        self.disk_threshold = disk_threshold

        # Build condition name
        conditions = []
        if memory_threshold:
            conditions.append(f"memory>{memory_threshold}%")
        if cpu_threshold:
            conditions.append(f"cpu>{cpu_threshold}%")
        if disk_threshold:
            conditions.append(f"disk>{disk_threshold}%")

        condition_name = f"resource_check({', '.join(conditions)})"

        super().__init__(
            condition=self._check_resources,
            check_interval=check_interval,
            condition_name=condition_name,
            name=name or "resource_monitor",
        )

    async def _check_resources(self) -> bool:
        """Check if any resource threshold is exceeded."""
        try:
            import psutil
        except ImportError:
            logger.warning("psutil not available, resource monitoring disabled")
            return False

        # Check memory
        if self.memory_threshold:
            memory_percent = psutil.virtual_memory().percent
            if memory_percent > self.memory_threshold:
                logger.info(
                    "Memory threshold exceeded",
                    extra={
                        "current": memory_percent,
                        "threshold": self.memory_threshold,
                    },
                )
                return True

        # Check CPU
        if self.cpu_threshold:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            if cpu_percent > self.cpu_threshold:
                logger.info(
                    "CPU threshold exceeded",
                    extra={
                        "current": cpu_percent,
                        "threshold": self.cpu_threshold,
                    },
                )
                return True

        # Check disk
        if self.disk_threshold:
            disk_usage = psutil.disk_usage("/").percent
            if disk_usage > self.disk_threshold:
                logger.info(
                    "Disk threshold exceeded",
                    extra={
                        "current": disk_usage,
                        "threshold": self.disk_threshold,
                    },
                )
                return True

        return False
