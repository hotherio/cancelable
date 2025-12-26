#!/usr/bin/env python3
"""
Simplified database operation examples with cancelation support.
"""

import os
import sys

# Add parent directory to path for imports when running directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

import asyncio
import random
from datetime import UTC, datetime, timedelta

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base

from hother.cancelable import Cancelable, cancelable
from hother.cancelable.integrations.sqlalchemy import cancelable_session

# Database models
Base = declarative_base()


class DataPoint(Base):
    __tablename__ = "data_points"

    id = Column(Integer, primary_key=True)
    name = Column(String(50), index=True)
    value = Column(Float)
    timestamp = Column(DateTime, default=lambda: datetime.now(UTC))
    processed = Column(Boolean, default=False)


async def setup_simple_database():
    """Setup simple in-memory database."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    print("✓ Database setup complete")
    return engine


async def create_test_data(engine, count: int = 500):
    """Create test data."""
    print(f"Creating {count} test records...")

    async with AsyncSession(engine) as session:
        records = [
            DataPoint(
                name=f"sensor_{i % 10}",
                value=random.uniform(0, 100),
                timestamp=datetime.now(UTC) - timedelta(minutes=i),
            )
            for i in range(count)
        ]

        session.add_all(records)
        await session.commit()

    print(f"✓ Created {count} test records")


async def main():
    """Run all examples."""

    # Example 1: Basic database queries with cancelation
    try:
        engine = await setup_simple_database()
        await create_test_data(engine, 100)

        async with Cancelable.with_timeout(5.0, name="basic_queries") as cancel:
            async with cancelable_session(engine, cancel) as session:
                # Count total records
                total = await session.scalar(select(func.count()).select_from(DataPoint))
                print(f"Total records: {total}")

                # Get recent records
                recent = await session.execute(select(DataPoint).order_by(DataPoint.timestamp.desc()).limit(5))
                records = recent.scalars().all()

                print(f"Recent records: {len(records)}")
                for record in records:
                    print(f"  {record.name}: {record.value:.2f}")
    except Exception as e:
        print(f"❌ Example failed: {e}")
    print()

    # Example 2: Process data in batches with cancelation
    try:
        engine = await setup_simple_database()
        await create_test_data(engine, 200)

        @cancelable(timeout=10.0, name="batch_processor")
        async def process_batch(batch_size: int = 50, *, cancelable: Cancelable):
            async with cancelable_session(engine, cancelable) as session:
                # Process unprocessed records
                processed_total = 0

                while True:
                    # Get next batch
                    result = await session.execute(select(DataPoint).where(DataPoint.processed == False).limit(batch_size))
                    batch = result.scalars().all()

                    if not batch:
                        break

                    # Process batch
                    for record in batch:
                        record.processed = True
                        record.value = record.value * 1.1  # Apply some processing

                    await session.commit()
                    processed_total += len(batch)

                    await cancelable.report_progress(
                        f"Processed batch of {len(batch)} records", {"total_processed": processed_total}
                    )

                    # Small delay to show cancelation works
                    await asyncio.sleep(0.1)

                return processed_total

        try:
            total_processed = await process_batch()
            print(f"✓ Successfully processed {total_processed} records")
        except asyncio.CancelledError:
            print("⚠️ Processing was cancelled")
    except Exception as e:
        print(f"❌ Example failed: {e}")
    print()

    # Example 3: Long operation with progress reporting
    try:
        engine = await setup_simple_database()
        await create_test_data(engine, 300)

        progress_messages = []

        def capture_progress(op_id, msg, meta):
            progress_messages.append(msg)
            print(f"  📊 {msg}")

        async with Cancelable().on_progress(capture_progress) as cancel:
            async with cancelable_session(engine, cancel) as session:
                # Calculate statistics for each sensor
                sensors = [f"sensor_{i}" for i in range(10)]

                for i, sensor in enumerate(sensors):
                    # Query data for this sensor
                    result = await session.execute(select(DataPoint).where(DataPoint.name == sensor))
                    records = result.scalars().all()

                    if records:
                        avg_value = sum(r.value for r in records) / len(records)
                        await cancel.report_progress(
                            f"Sensor {sensor}: {len(records)} records, avg={avg_value:.2f}",
                            {"sensor": sensor, "count": len(records), "average": avg_value},
                        )

                    # Small delay
                    await asyncio.sleep(0.05)

        print(f"✓ Generated {len(progress_messages)} progress reports")
    except Exception as e:
        print(f"Example failed: {e}", exc_info=True)
    print()

    # Example 4: Operation that gets cancelled
    try:
        engine = await setup_simple_database()
        await create_test_data(engine, 1000)

        try:
            async with Cancelable.with_timeout(0.2, name="quick_timeout") as cancel:
                async with cancelable_session(engine, cancel) as session:
                    # This should timeout
                    for i in range(100):
                        # Simulate slow processing - use proper parameter names
                        result = await session.execute(select(DataPoint).limit(10).offset(i * 10))
                        records = result.scalars().all()

                        for record in records:
                            record.value = record.value + 1

                        await session.flush()
                        await asyncio.sleep(0.05)  # This will cause timeout

                    await session.commit()
                    print("This should not print!")

        except asyncio.CancelledError:
            print("✓ Operation was cancelled as expected")
            print(f"  Reason: {cancel.context.cancel_reason}")
            print(f"  Duration: {cancel.context.duration}")
    except Exception as e:
        print(f"Example failed: {e}", exc_info=True)
    print()


if __name__ == "__main__":
    asyncio.run(main())
