"""
Composite cancelation source for combining multiple sources.
"""


import anyio

from hother.cancelable.core.models import CancelationReason
from hother.cancelable.sources.base import CancelationSource
from hother.cancelable.utils.logging import get_logger

logger = get_logger(__name__)


class CompositeSource(CancelationSource):
    """
    Cancelation source that combines multiple other sources.

    Triggers when any of the component sources trigger.
    """

    def __init__(
        self,
        sources: list[CancelationSource],
        name: str | None = None,
    ):
        """
        Initialize composite source.

        Args:
            sources: List of cancelation sources to combine
            name: Optional name for the source
        """
        # Use MANUAL as default reason (will be overridden by actual source)
        super().__init__(CancelationReason.MANUAL, name or "composite")

        if not sources:
            raise ValueError("At least one source is required")

        self.sources = sources
        self.triggered_source: CancelationSource | None = None

    async def start_monitoring(self, scope: anyio.CancelScope) -> None:
        """
        Start monitoring all component sources.

        Args:
            scope: Cancel scope to trigger when any source triggers
        """
        self.scope = scope

        # Create task group for background monitoring
        self._task_group = anyio.create_task_group()
        await self._task_group.__aenter__()

        # Start each source with a wrapper
        for source in self.sources:
            self._task_group.start_soon(self._monitor_source, source)

        logger.debug(
            "Composite source activated: %s with %d sources (%s)",
            self.name,
            len(self.sources),
            [type(s).__name__ for s in self.sources],
        )

    async def stop_monitoring(self) -> None:
        """Stop monitoring all component sources."""
        # Cancel monitoring task group
        if hasattr(self, "_task_group") and self._task_group:
            self._task_group.cancel_scope.cancel()

            # Try to properly exit the task group, but shield from cancelation
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

        # Stop each source
        for source in self.sources:
            try:
                await source.stop_monitoring()
            except Exception as e:
                logger.error(
                    "Error stopping source %s: %s",
                    str(source),
                    str(e),
                    exc_info=True,
                )

        logger.debug(
            "Composite source stopped: %s (triggered by %s)",
            self.name,
            str(self.triggered_source) if self.triggered_source else None,
        )

    async def _monitor_source(self, source: CancelationSource) -> None:
        """
        Monitor a single source and propagate its cancelation.

        Args:
            source: Source to monitor
        """
        # Override the source's trigger method to capture which source triggered
        original_trigger = source.trigger_cancelation

        async def wrapped_trigger(message: str | None = None):
            self.triggered_source = source
            self.reason = source.reason  # Use the source's reason
            await original_trigger(message)

            # Trigger our own cancelation
            if self.scope and not self.scope.cancel_called:
                await self.trigger_cancelation(f"Composite source triggered by {source.name}: {message}")

        source.trigger_cancelation = wrapped_trigger

        try:
            # Start the source
            await source.start_monitoring(anyio.CancelScope())
        except Exception as e:
            logger.error(
                "Error in component source %s of composite %s: %s",
                str(source),
                self.name,
                str(e),
                exc_info=True,
            )


class AnyOfSource(CompositeSource):
    """Alias for CompositeSource - triggers when ANY source triggers."""


class AllOfSource(CancelationSource):
    """
    Cancelation source that requires ALL component sources to trigger.

    Only cancels when all component sources have triggered.
    """

    def __init__(
        self,
        sources: list[CancelationSource],
        name: str | None = None,
    ):
        """
        Initialize all-of source.

        Args:
            sources: List of cancelation sources that must all trigger
            name: Optional name for the source
        """
        super().__init__(CancelationReason.MANUAL, name or "all_of")

        if not sources:
            raise ValueError("At least one source is required")

        self.sources = sources
        self.triggered_sources: set[CancelationSource] = set()
        self._lock = anyio.Lock()

    async def start_monitoring(self, scope: anyio.CancelScope) -> None:
        """Start monitoring all component sources."""
        self.scope = scope

        # Create a task group for all sources
        self._task_group = anyio.create_task_group()
        await self._task_group.__aenter__()

        # Start each source with a wrapper
        for source in self.sources:
            self._task_group.start_soon(self._monitor_source, source)

        logger.debug(
            "All-of source activated: %s with %d sources",
            self.name,
            len(self.sources),
        )

    async def stop_monitoring(self) -> None:
        """Stop monitoring all component sources."""
        # Cancel monitoring task group
        if hasattr(self, "_task_group") and self._task_group:
            self._task_group.cancel_scope.cancel()
            await self._task_group.__aexit__(None, None, None)

        # Stop each source
        for source in self.sources:
            try:
                await source.stop_monitoring()
            except Exception as e:
                logger.error(
                    "Error stopping source %s: %s",
                    str(source),
                    str(e),
                    exc_info=True,
                )

    async def _monitor_source(self, source: CancelationSource) -> None:
        """Monitor a single source and check if all have triggered."""
        # Override the source's trigger method
        original_trigger = source.trigger_cancelation

        async def wrapped_trigger(message: str | None = None):
            async with self._lock:
                self.triggered_sources.add(source)

                # Check if all sources have triggered
                if len(self.triggered_sources) == len(self.sources):
                    # All sources triggered, cancel
                    await self.trigger_cancelation(f"All {len(self.sources)} sources have triggered")

            # Still call original trigger for logging
            await original_trigger(message)

        source.trigger_cancelation = wrapped_trigger

        try:
            # Start the source with a dummy scope
            await source.start_monitoring(anyio.CancelScope())
        except Exception as e:
            logger.error(
                "Error in component source %s of all-of %s: %s",
                str(source),
                self.name,
                str(e),
                exc_info=True,
            )
