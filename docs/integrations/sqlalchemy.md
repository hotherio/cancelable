# SQLAlchemy Integration

The cancelable library provides integration with SQLAlchemy for cancellable database operations, supporting both async and sync database sessions.

## Installation

The SQLAlchemy integration is included when you install cancelable:

```bash
uv add hother-cancelable
```

## Basic Usage

### Cancellable Database Session

```python
from sqlalchemy.ext.asyncio import create_async_engine
from hother.cancelable import Cancellable
from hother.cancelable.integrations.sqlalchemy import cancellable_session

# Create async engine
engine = create_async_engine("sqlite+aiosqlite:///example.db")

async with Cancellable.with_timeout(30.0) as cancel:
    async with cancellable_session(engine, cancel) as session:
        # Execute queries with cancellation support
        result = await session.execute(
            select(User).where(User.active == True)
        )
        users = result.scalars().all()
```

### Long-Running Queries

```python
async def process_large_dataset():
    async with Cancellable.with_timeout(300.0) as cancel:
        cancel.on_progress(
            lambda op_id, msg, meta: logger.info(f"Query progress: {msg}")
        )
        
        async with cancellable_session(engine, cancel) as session:
            # Process in batches with cancellation checks
            offset = 0
            batch_size = 1000
            total_processed = 0
            
            while True:
                result = await session.execute(
                    select(Order)
                    .limit(batch_size)
                    .offset(offset)
                )
                
                orders = result.scalars().all()
                if not orders:
                    break
                
                # Process batch
                for order in orders:
                    await process_order(order)
                    total_processed += 1
                
                # Report progress
                await cancel.report_progress(
                    f"Processed {total_processed} orders",
                    {"count": total_processed, "batch": offset // batch_size}
                )
                
                offset += batch_size
                
                # Commit after each batch
                await session.commit()
```

## Advanced Features

### Transaction Management with Cancellation

```python
async with Cancellable.with_timeout(60.0) as cancel:
    async with cancellable_session(engine, cancel) as session:
        try:
            # Start transaction
            async with session.begin():
                # Multiple operations in transaction
                user = User(name="John Doe", email="john@example.com")
                session.add(user)
                
                # Simulate long operation
                await cancel.report_progress("Creating user account")
                
                profile = UserProfile(user_id=user.id, bio="New user")
                session.add(profile)
                
                # Transaction automatically commits on success
                
        except CancelledError:
            # Transaction automatically rolls back on cancellation
            logger.warning("Transaction cancelled, rolling back")
            raise
```

### Streaming Large Results

```python
async def stream_query_results():
    async with Cancellable.with_timeout(120.0) as cancel:
        async with cancellable_session(engine, cancel) as session:
            # Use stream_scalars for memory-efficient processing
            async with session.stream_scalars(
                select(LogEntry).order_by(LogEntry.timestamp)
            ) as result:
                async for log_entry in result:
                    # Process each row individually
                    await process_log_entry(log_entry)
                    
                    # Cancellation is checked between iterations
```

### Bulk Operations with Progress

```python
async def bulk_insert_with_cancellation(items: list[dict]):
    async with Cancellable.with_timeout(300.0) as cancel:
        cancel.on_progress(
            lambda op_id, msg, meta: print(f"Bulk insert: {msg}")
        )
        
        async with cancellable_session(engine, cancel) as session:
            # Process in chunks
            chunk_size = 1000
            total_inserted = 0
            
            for i in range(0, len(items), chunk_size):
                chunk = items[i:i + chunk_size]
                
                # Bulk insert
                await session.execute(
                    insert(Product),
                    chunk
                )
                
                total_inserted += len(chunk)
                
                # Report progress
                await cancel.report_progress(
                    f"Inserted {total_inserted}/{len(items)} items",
                    {
                        "inserted": total_inserted,
                        "total": len(items),
                        "percent": (total_inserted / len(items)) * 100
                    }
                )
                
                # Commit after each chunk
                await session.commit()
```

## Connection Pool Management

### Cancellable Pool Configuration

```python
from sqlalchemy.pool import NullPool

# Create engine with custom pool settings
engine = create_async_engine(
    "postgresql+asyncpg://user:pass@localhost/db",
    pool_pre_ping=True,  # Test connections before use
    pool_size=20,
    max_overflow=10,
    pool_timeout=30,  # Wait max 30s for connection
)

async def get_connection_with_cancel():
    async with Cancellable.with_timeout(5.0) as cancel:
        # Cancel if can't get connection within 5 seconds
        async with cancellable_session(engine, cancel) as session:
            return await session.execute(select(1))
```

## Error Handling

### Handling Database Errors with Cancellation

```python
from sqlalchemy.exc import DBAPIError, IntegrityError
from hother.cancelable import TimeoutCancellation

async def safe_database_operation():
    try:
        async with Cancellable.with_timeout(30.0) as cancel:
            async with cancellable_session(engine, cancel) as session:
                # Database operations
                result = await session.execute(query)
                await session.commit()
                return result
                
    except TimeoutCancellation:
        logger.error("Database operation timed out")
        # Handle timeout appropriately
        raise
        
    except IntegrityError as e:
        logger.error(f"Integrity constraint violated: {e}")
        # Handle constraint violations
        raise
        
    except DBAPIError as e:
        logger.error(f"Database error: {e}")
        # Handle other database errors
        raise
```

## Best Practices

1. **Use appropriate timeouts**: Set timeouts based on expected query duration
2. **Process in batches**: For large datasets, process in manageable chunks
3. **Check cancellation regularly**: In long loops, ensure cancellation is checked
4. **Clean up resources**: Sessions are automatically cleaned up on cancellation
5. **Use streaming for large results**: Prevent memory issues with stream_scalars

## Example: ETL Pipeline with Cancellation

```python
async def etl_pipeline(source_engine, target_engine, cancel_token):
    """Extract, transform, and load data with cancellation support."""
    
    async with Cancellable.with_token(cancel_token) as cancel:
        cancel.on_progress(
            lambda op_id, msg, meta: logger.info(f"ETL: {msg}", **meta)
        )
        
        # Extract
        await cancel.report_progress("Starting extraction")
        async with cancellable_session(source_engine, cancel) as source_session:
            data = await source_session.execute(
                select(SourceTable).where(SourceTable.processed == False)
            )
            records = data.scalars().all()
        
        await cancel.report_progress(f"Extracted {len(records)} records")
        
        # Transform
        await cancel.report_progress("Starting transformation")
        transformed = []
        for i, record in enumerate(records):
            transformed_record = await transform_record(record)
            transformed.append(transformed_record)
            
            if i % 100 == 0:
                await cancel.report_progress(
                    f"Transformed {i}/{len(records)} records"
                )
        
        # Load
        await cancel.report_progress("Starting load")
        async with cancellable_session(target_engine, cancel) as target_session:
            # Bulk insert transformed data
            await target_session.execute(
                insert(TargetTable),
                transformed
            )
            await target_session.commit()
        
        await cancel.report_progress(f"ETL completed: {len(records)} records processed")
```

## Integration with Alembic Migrations

```python
from alembic import command
from alembic.config import Config

async def run_migrations_with_timeout():
    """Run database migrations with timeout."""
    
    async with Cancellable.with_timeout(300.0) as cancel:
        cancel.on_progress(
            lambda op_id, msg, meta: logger.info(f"Migration: {msg}")
        )
        
        # Note: Alembic migrations are synchronous
        # We can still use cancellation for the overall timeout
        alembic_cfg = Config("alembic.ini")
        
        await cancel.report_progress("Starting migrations")
        
        # Run in thread pool to avoid blocking
        await asyncio.to_thread(
            command.upgrade,
            alembic_cfg,
            "head"
        )
        
        await cancel.report_progress("Migrations completed")
```