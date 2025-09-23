"""
Composite cancellation source for combining multiple sources.
"""


import anyio

from cancelable.core.models import CancellationReason
from cancelable.sources.base import CancellationSource
from cancelable.utils.logging import get_logger

logger = get_logger(__name__)


class CompositeSource(CancellationSource):
    """
    Cancellation source that combines multiple other sources.

    Triggers when any of the component sources trigger.
    """

    def __init__(
        self,
        sources: list[CancellationSource],
        name: str | None = None,
    ):
        """
        Initialize composite source.

        Args:
            sources: List of cancellation sources to combine
            name: Optional name for the source
        """
        # Use MANUAL as default reason (will be overridden by actual source)
        super().__init__(CancellationReason.MANUAL, name or "composite")

        if not sources:
            raise ValueError("At least one source is required")

        self.sources = sources
        self.triggered_source: CancellationSource | None = None

    async def start_monitoring(self, scope: anyio.CancelScope) -> None:
        """
        Start monitoring all component sources.

        Args:
            scope: Cancel scope to trigger when any source triggers
        """
        self.scope = scope
        self._monitoring_tasks = []

        # Start each source with a wrapper
        import asyncio

        for source in self.sources:
            task = asyncio.create_task(self._monitor_source(source))
            self._monitoring_tasks.append(task)

        logger.debug(
            "Composite source activated",
            source=self.name,
            source_count=len(self.sources),
            source_types=[type(s).__name__ for s in self.sources],
        )

    async def stop_monitoring(self) -> None:
        """Stop monitoring all component sources."""
        # Cancel monitoring tasks
        if hasattr(self, "_monitoring_tasks"):
            for task in self._monitoring_tasks:
                task.cancel()

            # Wait for all tasks to complete
            for task in self._monitoring_tasks:
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Stop each source
        for source in self.sources:
            try:
                await source.stop_monitoring()
            except Exception as e:
                logger.error(
                    "Error stopping source",
                    source=str(source),
                    error=str(e),
                    exc_info=True,
                )

        logger.debug(
            "Composite source stopped",
            source=self.name,
            triggered_source=str(self.triggered_source) if self.triggered_source else None,
        )

    async def _monitor_source(self, source: CancellationSource) -> None:
        """
        Monitor a single source and propagate its cancellation.

        Args:
            source: Source to monitor
        """
        # Override the source's trigger method to capture which source triggered
        original_trigger = source.trigger_cancellation

        async def wrapped_trigger(message: str | None = None):
            self.triggered_source = source
            self.reason = source.reason  # Use the source's reason
            await original_trigger(message)

            # Trigger our own cancellation
            if self.scope and not self.scope.cancel_called:
                await self.trigger_cancellation(f"Composite source triggered by {source.name}: {message}")

        source.trigger_cancellation = wrapped_trigger

        try:
            # Start the source
            await source.start_monitoring(anyio.CancelScope())
        except Exception as e:
            logger.error(
                "Error in component source",
                composite_source=self.name,
                component_source=str(source),
                error=str(e),
                exc_info=True,
            )


class AnyOfSource(CompositeSource):
    """Alias for CompositeSource - triggers when ANY source triggers."""


class AllOfSource(CancellationSource):
    """
    Cancellation source that requires ALL component sources to trigger.

    Only cancels when all component sources have triggered.
    """

    def __init__(
        self,
        sources: list[CancellationSource],
        name: str | None = None,
    ):
        """
        Initialize all-of source.

        Args:
            sources: List of cancellation sources that must all trigger
            name: Optional name for the source
        """
        super().__init__(CancellationReason.MANUAL, name or "all_of")

        if not sources:
            raise ValueError("At least one source is required")

        self.sources = sources
        self.triggered_sources: set[CancellationSource] = set()
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
            "All-of source activated",
            source=self.name,
            source_count=len(self.sources),
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
                    "Error stopping source",
                    source=str(source),
                    error=str(e),
                    exc_info=True,
                )

    async def _monitor_source(self, source: CancellationSource) -> None:
        """Monitor a single source and check if all have triggered."""
        # Override the source's trigger method
        original_trigger = source.trigger_cancellation

        async def wrapped_trigger(message: str | None = None):
            async with self._lock:
                self.triggered_sources.add(source)

                # Check if all sources have triggered
                if len(self.triggered_sources) == len(self.sources):
                    # All sources triggered, cancel
                    await self.trigger_cancellation(f"All {len(self.sources)} sources have triggered")

            # Still call original trigger for logging
            await original_trigger(message)

        source.trigger_cancellation = wrapped_trigger

        try:
            # Start the source with a dummy scope
            await source.start_monitoring(anyio.CancelScope())
        except Exception as e:
            logger.error(
                "Error in component source",
                all_of_source=self.name,
                component_source=str(source),
                error=str(e),
                exc_info=True,
            )
