#!/usr/bin/env python3
"""
Fixed database operation examples with proper SQLite handling.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

import asyncio
import random
import tempfile
from datetime import UTC, datetime, timedelta

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base

from hother.cancelable import Cancellable, cancellable
from hother.cancelable.integrations.sqlalchemy import cancellable_session
from hother.cancelable.utils.logging import configure_logging, get_logger

configure_logging(log_level="INFO")
logger = get_logger(__name__)

Base = declarative_base()


class SensorData(Base):
    __tablename__ = "sensor_data"

    id = Column(Integer, primary_key=True)
    sensor_id = Column(String(50), index=True)
    timestamp = Column(DateTime, index=True)
    value = Column(Float)
    processed = Column(Boolean, default=False)


async def create_engine_and_tables():
    """Create engine and tables reliably."""
    # Use a temporary file for the database
    temp_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db_path = temp_file.name
    temp_file.close()

    print(f"Using temporary database: {db_path}")

    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    return engine, db_path


async def populate_data(engine, count=500):
    """Populate test data."""
    print(f"Populating {count} records...")

    async with AsyncSession(engine) as session:
        base_time = datetime.now(UTC) - timedelta(hours=count)

        for i in range(count):
            record = SensorData(sensor_id=f"sensor_{i % 5}", timestamp=base_time + timedelta(hours=i), value=20.0 + random.gauss(0, 2), processed=False)
            session.add(record)

            # Commit in batches
            if (i + 1) % 100 == 0:
                await session.commit()
                print(f"  Inserted {i + 1} records...")

        await session.commit()

    print(f"✓ Populated {count} records")


async def example_basic_operations():
    """Basic database operations with cancellation."""
    print("\n=== Basic Operations Example ===")

    engine, db_path = await create_engine_and_tables()

    try:
        await populate_data(engine, 200)

        async with Cancellable.with_timeout(10.0) as cancel:
            async with cancellable_session(engine, cancel) as session:
                # Count records
                total = await session.scalar(select(func.count()).select_from(SensorData))
                print(f"Total records: {total}")

                # Get sample data
                result = await session.execute(select(SensorData).limit(5).order_by(SensorData.timestamp.desc()))
                records = result.scalars().all()

                print("Recent records:")
                for record in records:
                    print(f"  {record.sensor_id}: {record.value:.2f} at {record.timestamp}")

        print("✓ Basic operations completed")

    finally:
        await engine.dispose()
        if os.path.exists(db_path):
            os.unlink(db_path)


async def example_batch_processing():
    """Batch processing with progress reporting."""
    print("\n=== Batch Processing Example ===")

    engine, db_path = await create_engine_and_tables()

    try:
        await populate_data(engine, 300)

        progress_reports = []

        @cancellable(timeout=15.0)
        async def process_batches(cancellable: Cancellable = None):
            cancellable.on_progress(lambda op_id, msg, meta: progress_reports.append(msg))

            async with cancellable_session(engine, cancellable) as session:
                batch_size = 50
                processed = 0

                while True:
                    # Get unprocessed batch
                    result = await session.execute(select(SensorData).where(not SensorData.processed).limit(batch_size))
                    records = result.scalars().all()

                    if not records:
                        break

                    # Process records
                    for record in records:
                        record.processed = True
                        record.value = record.value * 1.1  # Some processing

                    await session.commit()
                    processed += len(records)

                    await cancellable.report_progress(f"Processed {processed} records", {"batch_size": len(records)})

                    # Small delay
                    await asyncio.sleep(0.05)

                return processed

        total = await process_batches()
        print(f"✓ Processed {total} records")
        print(f"Progress reports: {len(progress_reports)}")

    finally:
        await engine.dispose()
        if os.path.exists(db_path):
            os.unlink(db_path)


async def example_cancellation():
    """Example showing actual cancellation with proper cleanup."""
    print("\n=== Cancellation Example ===")

    engine, db_path = await create_engine_and_tables()

    try:
        await populate_data(engine, 500)

        processed_count = 0

        try:
            async with Cancellable.with_timeout(0.2) as cancel:  # Short timeout
                async with cancellable_session(engine, cancel) as session:
                    # Get records in smaller batches to avoid holding too many connections
                    batch_size = 50
                    offset = 0

                    while True:
                        # Get next batch
                        result = await session.execute(select(SensorData).limit(batch_size).offset(offset))
                        records = result.scalars().all()

                        if not records:
                            break

                        # Process batch
                        for record in records:
                            record.value = record.value + 1
                            processed_count += 1

                        # Commit batch
                        await session.commit()
                        offset += batch_size

                        # This delay will cause timeout
                        await asyncio.sleep(0.1)

                    print("This should not print!")

        except asyncio.CancelledError:
            print(f"✓ Operation cancelled after processing {processed_count} records")
            print("  Cancellation reason: Timeout")

    finally:
        # Ensure engine is properly disposed
        await engine.dispose()

        # Small delay to allow connections to close
        await asyncio.sleep(0.1)

        # Clean up file
        if os.path.exists(db_path):
            os.unlink(db_path)


async def main():
    """Run all examples."""
    print("Fixed Database Operations Examples")
    print("=================================")

    await example_basic_operations()
    await example_batch_processing()
    await example_cancellation()

    print("\n✅ All examples completed!")


if __name__ == "__main__":
    asyncio.run(main())
