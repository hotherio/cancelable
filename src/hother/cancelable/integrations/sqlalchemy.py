"""
SQLAlchemy integration for cancellable database operations.
"""

import asyncio
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import asynccontextmanager
from typing import Any, TypeVar

import anyio

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.sql import Select

from hother.cancelable.core.cancellable import Cancellable
from hother.cancelable.utils.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class CancellableAsyncSession:
    """
    SQLAlchemy async session wrapper with cancellation support.

    Provides automatic cancellation checking between database operations
    and progress reporting for bulk operations.
    """

    def __init__(
        self,
        session: AsyncSession,
        cancellable: Cancellable | None = None,
        check_interval: int = 100,
    ):
        """
        Initialize cancellable session.

        Args:
            session: SQLAlchemy async session
            cancellable: Cancellable instance
            check_interval: Check cancellation every N operations
        """
        self.session = session
        self.cancellable = cancellable
        self.check_interval = check_interval
        self._operation_count = 0

    async def _check_cancellation(self) -> None:
        """Check for cancellation periodically."""
        if self.cancellable:
            self._operation_count += 1
            if self._operation_count % self.check_interval == 0:
                await self.cancellable._token.check_async()
                await self.cancellable.report_progress(f"Database operations: {self._operation_count}")

    async def execute(self, statement, params=None, execution_options=None, **kw):
        """Execute statement with cancellation check."""
        await self._check_cancellation()
        return await self.session.execute(statement, params, execution_options=execution_options, **kw)

    async def scalar(self, statement, params=None, execution_options=None, **kw):
        """Execute and return scalar with cancellation check."""
        await self._check_cancellation()
        return await self.session.scalar(statement, params, execution_options=execution_options, **kw)

    async def scalars(self, statement, params=None, execution_options=None, **kw):
        """Execute and return scalars with cancellation check."""
        await self._check_cancellation()
        result = await self.session.scalars(statement, params, execution_options=execution_options, **kw)
        return result  # Return directly for now, wrapping might cause issues

    async def get(self, entity, ident, **kw):
        """Get entity by identity with cancellation check."""
        await self._check_cancellation()
        return await self.session.get(entity, ident, **kw)

    async def stream(self, statement, params=None, execution_options=None, **kw):
        """Stream results with cancellation support."""
        await self._check_cancellation()
        result = await self.session.stream(statement, params, execution_options=execution_options, **kw)
        return CancellableAsyncResult(result, self.cancellable)

    async def stream_scalars(self, statement, params=None, execution_options=None, **kw):
        """Stream scalars with cancellation support."""
        await self._check_cancellation()
        result = await self.session.stream_scalars(statement, params, execution_options=execution_options, **kw)
        return CancellableAsyncScalarResult(result, self.cancellable)

    def add(self, instance, _warn=True):
        """Add instance to session."""
        return self.session.add(instance, _warn)

    def add_all(self, instances):
        """Add multiple instances to session."""
        return self.session.add_all(instances)

    async def flush(self, objects=None):
        """Flush pending changes with cancellation check."""
        await self._check_cancellation()
        await self.session.flush(objects)

    async def commit(self):
        """Commit transaction with cancellation check."""
        await self._check_cancellation()
        if self.cancellable:
            await self.cancellable.report_progress("Committing transaction")
        await self.session.commit()

    async def rollback(self):
        """Rollback transaction."""
        if self.cancellable:
            await self.cancellable.report_progress("Rolling back transaction")
        await self.session.rollback()

    async def close(self):
        """Close session."""
        await self.session.close()

    def expunge(self, instance):
        """Expunge instance from session."""
        self.session.expunge(instance)

    def expunge_all(self):
        """Expunge all instances from session."""
        self.session.expunge_all()

    async def refresh(self, instance, attribute_names=None, with_for_update=None):
        """Refresh instance with cancellation check."""
        await self._check_cancellation()
        await self.session.refresh(instance, attribute_names, with_for_update)

    async def merge(self, instance, load=True, options=None):
        """Merge instance with cancellation check."""
        await self._check_cancellation()
        return await self.session.merge(instance, load, options)

    # Bulk operations with progress reporting
    async def bulk_insert_mappings(
        self,
        mapper,
        mappings: list[dict],
        return_defaults=False,
        render_nulls=False,
    ):
        """Bulk insert with progress reporting."""
        if self.cancellable:
            await self.cancellable.report_progress(f"Starting bulk insert of {len(mappings)} records")

        batch_size = 1000
        for i in range(0, len(mappings), batch_size):
            await self._check_cancellation()
            batch = mappings[i : i + batch_size]

            await self.session.bulk_insert_mappings(mapper, batch, return_defaults, render_nulls)

            if self.cancellable:
                await self.cancellable.report_progress(f"Inserted batch {i // batch_size + 1}: {len(batch)} records")

    async def bulk_update_mappings(self, mapper, mappings: list[dict]):
        """Bulk update with progress reporting."""
        if self.cancellable:
            await self.cancellable.report_progress(f"Starting bulk update of {len(mappings)} records")

        batch_size = 1000
        for i in range(0, len(mappings), batch_size):
            await self._check_cancellation()
            batch = mappings[i : i + batch_size]

            await self.session.bulk_update_mappings(mapper, batch)

            if self.cancellable:
                await self.cancellable.report_progress(f"Updated batch {i // batch_size + 1}: {len(batch)} records")

    @property
    def dirty(self):
        """Get dirty objects."""
        return self.session.dirty

    @property
    def deleted(self):
        """Get deleted objects."""
        return self.session.deleted

    @property
    def new(self):
        """Get new objects."""
        return self.session.new

    @property
    def is_active(self):
        """Check if session is active."""
        return self.session.is_active

    def __contains__(self, instance):
        """Check if instance is in session."""
        return instance in self.session


class CancellableAsyncResult:
    """Wrapper for async result with cancellation support."""

    def __init__(self, result, cancellable: Cancellable | None):
        self.result = result
        self.cancellable = cancellable
        self._row_count = 0

    async def __aiter__(self):
        """Iterate over results with cancellation checking."""
        async for row in self.result:
            if self.cancellable:
                await self.cancellable._token.check_async()

            self._row_count += 1
            if self.cancellable and self._row_count % 1000 == 0:
                await self.cancellable.report_progress(f"Processed {self._row_count} rows")

            yield row

    async def fetchall(self):
        """Fetch all results with cancellation checking."""
        results = []
        async for row in self:
            results.append(row)
        return results

    async def fetchone(self):
        """Fetch one result."""
        async for row in self:
            return row
        return None

    async def first(self):
        """Get first result."""
        return await self.fetchone()

    async def partitions(self, size=None):
        """Yield result partitions."""
        async for partition in self.result.partitions(size):
            if self.cancellable:
                await self.cancellable._token.check_async()
            yield partition


class CancellableScalarResult:
    """Wrapper for scalar result with cancellation support."""

    def __init__(self, result, cancellable: Cancellable | None):
        self.result = result
        self.cancellable = cancellable

    async def all(self) -> Sequence[Any]:
        """Get all scalars with cancellation checking."""
        if self.cancellable:
            await self.cancellable._token.check_async()
        return await self.result.all()

    async def first(self) -> Any | None:
        """Get first scalar."""
        if self.cancellable:
            await self.cancellable._token.check_async()
        return await self.result.first()

    async def one(self) -> Any:
        """Get exactly one scalar."""
        if self.cancellable:
            await self.cancellable._token.check_async()
        return await self.result.one()

    async def one_or_none(self) -> Any | None:
        """Get one scalar or None."""
        if self.cancellable:
            await self.cancellable._token.check_async()
        return await self.result.one_or_none()


class CancellableAsyncScalarResult:
    """Wrapper for async scalar result with cancellation support."""

    def __init__(self, result, cancellable: Cancellable | None):
        self.result = result
        self.cancellable = cancellable
        self._count = 0

    async def __aiter__(self):
        """Iterate over scalars with cancellation checking."""
        async for scalar in self.result:
            if self.cancellable:
                await self.cancellable._token.check_async()

            self._count += 1
            if self.cancellable and self._count % 1000 == 0:
                await self.cancellable.report_progress(f"Processed {self._count} scalars")

            yield scalar


@asynccontextmanager
async def cancellable_session(engine: AsyncEngine, cancellable: Cancellable, **session_kwargs) -> AsyncIterator[CancellableAsyncSession]:
    """
    Create a cancellable database session with proper cleanup.

    Args:
        engine: SQLAlchemy async engine
        cancellable: Cancellable instance
        **session_kwargs: Additional session arguments

    Yields:
        Cancellable session

    Example:
        async with Cancellable.with_timeout(30) as cancel:
            async with cancellable_session(engine, cancel) as session:
                result = await session.execute(select(User))
                users = result.scalars().all()
    """
    # Create session
    session = AsyncSession(engine, expire_on_commit=False, **session_kwargs)

    wrapped = CancellableAsyncSession(session, cancellable)

    try:
        yield wrapped
        # Only commit if we complete successfully
        await session.commit()
    except anyio.get_cancelled_exc_class():
        # Handle cancellation gracefully
        logger.info("Session cancelled, rolling back")
        try:
            await session.rollback()
        except Exception as e:
            logger.warning(f"Error during rollback: {e}")
        raise
    except (SQLAlchemyError, anyio.get_cancelled_exc_class()):
        # Handle database and cancellation exceptions
        try:
            await session.rollback()
        except Exception as e:
            logger.warning(f"Error during rollback: {e}")
        raise
    finally:
        # Always try to close the session
        try:
            await session.close()
        except Exception as e:
            logger.warning(f"Error closing session: {e}")


class CancellableTransaction:
    """
    Cancellable transaction context manager.

    Automatically rolls back on cancellation.
    """

    def __init__(
        self,
        session: CancellableAsyncSession,
        nested: bool = False,
    ):
        """
        Initialize cancellable transaction.

        Args:
            session: Cancellable session
            nested: Whether this is a nested transaction
        """
        self.session = session
        self.nested = nested
        self._transaction = None

    async def __aenter__(self):
        """Begin transaction."""
        if self.session.cancellable:
            await self.session.cancellable.report_progress("Beginning transaction" + (" (nested)" if self.nested else ""))

        if self.nested:
            self._transaction = await self.session.session.begin_nested()
        else:
            self._transaction = await self.session.session.begin()

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Commit or rollback transaction."""
        if exc_type is not None:
            # Rollback on any exception
            if self.session.cancellable:
                await self.session.cancellable.report_progress(f"Rolling back transaction: {exc_type.__name__}")
            await self._transaction.rollback()
        else:
            # Commit on success
            if self.session.cancellable:
                await self.session.cancellable.report_progress("Committing transaction")
            await self._transaction.commit()


async def execute_chunked(
    session: CancellableAsyncSession,
    query: Select,
    chunk_size: int = 1000,
    process_chunk: Callable | None = None,
) -> int:
    """
    Execute query in chunks with cancellation support.

    Args:
        session: Cancellable session
        query: SQLAlchemy select query
        chunk_size: Size of chunks to process
        process_chunk: Optional async function to process each chunk

    Returns:
        Total number of rows processed

    Example:
        async def process_users(users):
            for user in users:
                user.processed = True

        total = await execute_chunked(
            session,
            select(User).where(User.active == True),
            chunk_size=500,
            process_chunk=process_users
        )
    """
    total_count = 0
    offset = 0

    while True:
        # Check cancellation
        if session.cancellable:
            await session.cancellable._token.check_async()

        # Get chunk
        chunk_query = query.limit(chunk_size).offset(offset)
        result = await session.execute(chunk_query)
        rows = result.scalars().all()

        if not rows:
            break

        # Process chunk if handler provided
        if process_chunk:
            await process_chunk(rows)

        total_count += len(rows)
        offset += chunk_size

        # Report progress
        if session.cancellable:
            await session.cancellable.report_progress(f"Processed {total_count} rows", {"chunk_size": len(rows), "offset": offset})

        # If we got less than chunk_size, we're done
        if len(rows) < chunk_size:
            break

    return total_count
