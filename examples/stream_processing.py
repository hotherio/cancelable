#!/usr/bin/env python3
"""
Stream processing examples with async cancellation.
"""

import random
from datetime import datetime
from typing import AsyncIterator, List, Optional

import anyio

from hother.cancelable import Cancellable, CancellationToken
from hother.cancelable.utils.streams import chunked_cancellable_stream
from hother.cancelable.utils.logging import configure_logging, get_logger

# Configure logging
configure_logging(log_level="INFO")
logger = get_logger(__name__)


async def sensor_data_stream(
    sensor_id: str,
    interval: float = 0.1,
    error_rate: float = 0.05,
) -> AsyncIterator[dict]:
    """
    Simulate a sensor data stream.

    Args:
        sensor_id: Sensor identifier
        interval: Time between readings
        error_rate: Probability of error per reading
    """
    reading_count = 0

    while True:
        await anyio.sleep(interval)
        reading_count += 1

        # Simulate occasional errors
        if random.random() < error_rate:
            yield {
                "sensor_id": sensor_id,
                "timestamp": datetime.utcnow().isoformat(),
                "reading": reading_count,
                "error": "Sensor malfunction",
            }
        else:
            # Normal reading
            temperature = 20 + random.gauss(0, 2)  # 20°C ± 2°C
            humidity = 50 + random.gauss(0, 5)  # 50% ± 5%

            yield {
                "sensor_id": sensor_id,
                "timestamp": datetime.utcnow().isoformat(),
                "reading": reading_count,
                "temperature": round(temperature, 2),
                "humidity": round(humidity, 2),
            }


async def example_basic_stream_processing():
    """Example: Basic stream processing with cancellation."""
    print("\n=== Basic Stream Processing ===")

    # Process sensor stream with timeout
    async with Cancellable.with_timeout(5.0, name="sensor_processing") as cancel:
        cancel.on_progress(lambda op_id, msg, meta: print(f"  {msg}"))

        readings = []
        errors = 0

        async for data in cancel.stream(sensor_data_stream("SENSOR-001", interval=0.2), report_interval=10):
            if "error" in data:
                errors += 1
                print(f"  ⚠️  Error: {data['error']}")
            else:
                readings.append(data)
                if len(readings) % 5 == 0:
                    avg_temp = sum(r["temperature"] for r in readings[-5:]) / 5
                    print(f"  📊 Last 5 readings avg temp: {avg_temp:.1f}°C")

        print(f"  Total readings: {len(readings)}, Errors: {errors}")


async def example_multi_stream_merge():
    """Example: Merge multiple streams with cancellation."""
    print("\n=== Multi-Stream Merge ===")

    async def merge_streams(*streams: AsyncIterator) -> AsyncIterator:
        """Merge multiple async streams."""
        async with anyio.create_task_group() as tg:
            queue = anyio.create_memory_object_stream(100)
            send_stream, receive_stream = queue

            async def forward_stream(stream, stream_id):
                async with send_stream:
                    async for item in stream:
                        await send_stream.send((stream_id, item))

            # Start forwarding tasks
            for i, stream in enumerate(streams):
                tg.start_soon(forward_stream, stream, f"stream_{i}")

            # Yield merged items
            async with receive_stream:
                async for item in receive_stream:
                    yield item

    # Create multiple sensor streams
    sensors = [sensor_data_stream(f"SENSOR-{i:03d}", interval=0.3) for i in range(3)]

    # Process merged stream
    async with Cancellable.with_timeout(5.0, name="multi_sensor") as cancel:
        reading_counts = {}

        async for stream_id, data in cancel.stream(merge_streams(*sensors)):
            sensor = data["sensor_id"]
            reading_counts[sensor] = reading_counts.get(sensor, 0) + 1

            # Print periodic summary
            total = sum(reading_counts.values())
            if total % 10 == 0:
                summary = ", ".join(f"{k}: {v}" for k, v in reading_counts.items())
                print(f"  📊 Readings: {summary}")


async def example_stream_transformation():
    """Example: Stream transformation pipeline."""
    print("\n=== Stream Transformation Pipeline ===")

    async def validate_reading(data: dict) -> Optional[dict]:
        """Validate sensor reading."""
        if "error" in data:
            return None

        # Check ranges
        if not (0 <= data["temperature"] <= 50):
            logger.warning(f"Temperature out of range: {data['temperature']}")
            return None

        if not (0 <= data["humidity"] <= 100):
            logger.warning(f"Humidity out of range: {data['humidity']}")
            return None

        return data

    async def enrich_reading(data: dict) -> dict:
        """Enrich reading with calculated fields."""
        data = data.copy()

        # Calculate dew point (simplified formula)
        temp = data["temperature"]
        humidity = data["humidity"]
        dew_point = temp - ((100 - humidity) / 5)
        data["dew_point"] = round(dew_point, 2)

        # Add comfort level
        if 18 <= temp <= 24 and 40 <= humidity <= 60:
            data["comfort"] = "optimal"
        elif 16 <= temp <= 26 and 30 <= humidity <= 70:
            data["comfort"] = "good"
        else:
            data["comfort"] = "poor"

        return data

    # Create transformation pipeline
    async def transform_pipeline(stream: AsyncIterator[dict]) -> AsyncIterator[dict]:
        """Apply transformations to stream."""
        async for data in stream:
            # Validate
            validated = await validate_reading(data)
            if validated is None:
                continue

            # Enrich
            enriched = await enrich_reading(validated)

            yield enriched

    # Process with pipeline
    cancellable = Cancellable.with_timeout(5.0, name="transform_pipeline").on_progress(lambda op_id, msg, meta: logger.info(msg, **meta))

    async with cancellable:
        comfort_stats = {"optimal": 0, "good": 0, "poor": 0}

        pipeline = transform_pipeline(sensor_data_stream("SENSOR-001", interval=0.1, error_rate=0.02))

        async for reading in cancellable.stream(pipeline, report_interval=20):
            comfort_stats[reading["comfort"]] += 1

            # Print sample readings
            if sum(comfort_stats.values()) % 10 == 0:
                print(f"  🌡️  T: {reading['temperature']}°C, H: {reading['humidity']}%, DP: {reading['dew_point']}°C, Comfort: {reading['comfort']}")

        print(f"\n  Comfort statistics: {comfort_stats}")


async def example_chunked_processing():
    """Example: Process stream in chunks."""
    print("\n=== Chunked Stream Processing ===")

    async def process_batch(readings: List[dict]) -> dict:
        """Process a batch of readings."""
        if not readings:
            return {}

        temperatures = [r["temperature"] for r in readings if "temperature" in r]
        humidities = [r["humidity"] for r in readings if "humidity" in r]

        return {
            "batch_size": len(readings),
            "avg_temperature": round(sum(temperatures) / len(temperatures), 2) if temperatures else None,
            "avg_humidity": round(sum(humidities) / len(humidities), 2) if humidities else None,
            "min_temperature": round(min(temperatures), 2) if temperatures else None,
            "max_temperature": round(max(temperatures), 2) if temperatures else None,
            "timestamp": datetime.utcnow().isoformat(),
        }

    # Process in chunks
    async with Cancellable.with_timeout(10.0, name="chunked_processing") as cancel:
        stream = sensor_data_stream("SENSOR-001", interval=0.05)

        batch_count = 0
        async for chunk in chunked_cancellable_stream(stream, chunk_size=20, cancellable=cancel):
            batch_count += 1

            # Process batch
            summary = await process_batch(chunk)

            print(f"\n  📦 Batch {batch_count}:")
            print(f"     Size: {summary['batch_size']} readings")
            print(f"     Avg temp: {summary['avg_temperature']}°C")
            print(f"     Temp range: {summary['min_temperature']}°C - {summary['max_temperature']}°C")
            print(f"     Avg humidity: {summary['avg_humidity']}%")


async def example_backpressure_handling():
    """Example: Handle backpressure in stream processing."""
    print("\n=== Backpressure Handling ===")

    async def slow_processor(data: dict) -> dict:
        """Simulate slow processing."""
        # Simulate variable processing time
        processing_time = random.uniform(0.1, 0.3)
        await anyio.sleep(processing_time)

        return {
            **data,
            "processed_at": datetime.utcnow().isoformat(),
            "processing_time": processing_time,
        }

    # Create buffered processor
    async def buffered_processing(
        stream: AsyncIterator[dict],
        buffer_size: int = 10,
    ) -> AsyncIterator[dict]:
        """Process stream with buffering."""
        send_stream, receive_stream = anyio.create_memory_object_stream(buffer_size)

        async def producer():
            async with send_stream:
                async for item in stream:
                    try:
                        send_stream.send_nowait(item)
                    except anyio.WouldBlock:
                        logger.warning("Buffer full, dropping reading")
                        # In real app, might want to handle this differently

        async def consumer():
            async with receive_stream:
                async for item in receive_stream:
                    processed = await slow_processor(item)
                    yield processed

        async with anyio.create_task_group() as tg:
            tg.start_soon(producer)
            async for item in consumer():
                yield item

    # Process with backpressure handling
    token = CancellationToken()

    async def monitor_progress():
        """Monitor and potentially cancel if too slow."""
        await anyio.sleep(5.0)
        print("  ⏰ Time limit reached, cancelling...")
        await token.cancel()

    async with anyio.create_task_group() as tg:
        tg.start_soon(monitor_progress)

        try:
            async with Cancellable.with_token(token, name="backpressure_demo") as cancel:
                stream = sensor_data_stream("SENSOR-001", interval=0.05)
                processed_count = 0

                async for reading in cancel.stream(buffered_processing(stream)):
                    processed_count += 1

                    # Estimate dropped readings based on timing
                    expected_readings = (datetime.fromisoformat(reading["processed_at"]) - datetime.fromisoformat(reading["timestamp"])).total_seconds() / 0.05

                    if expected_readings > 1.5:
                        logger.warning("Possible dropped readings due to slow processing")

                    if processed_count % 10 == 0:
                        print(f"  ✅ Processed: {processed_count} readings")

        except anyio.get_cancelled_exc_class():
            print(f"  🛑 Processing cancelled after {processed_count} readings")


async def example_stateful_stream_processing():
    """Example: Stateful stream processing with cancellation."""
    print("\n=== Stateful Stream Processing ===")

    class TemperatureMonitor:
        """Monitor temperature trends."""

        def __init__(self, window_size: int = 10):
            self.window_size = window_size
            self.readings = []
            self.alerts = []

        async def process(self, reading: dict) -> Optional[dict]:
            """Process reading and detect anomalies."""
            if "temperature" not in reading:
                return None

            temp = reading["temperature"]
            self.readings.append(temp)

            # Keep window size
            if len(self.readings) > self.window_size:
                self.readings.pop(0)

            # Need at least 3 readings
            if len(self.readings) < 3:
                return None

            # Calculate statistics
            avg = sum(self.readings) / len(self.readings)
            std_dev = (sum((x - avg) ** 2 for x in self.readings) / len(self.readings)) ** 0.5

            # Detect anomalies
            if abs(temp - avg) > 2 * std_dev:
                alert = {
                    "type": "temperature_anomaly",
                    "timestamp": reading["timestamp"],
                    "value": temp,
                    "average": round(avg, 2),
                    "std_dev": round(std_dev, 2),
                    "severity": "high" if abs(temp - avg) > 3 * std_dev else "medium",
                }
                self.alerts.append(alert)
                return alert

            return None

    # Process with stateful monitor
    async with Cancellable.with_timeout(10.0, name="anomaly_detection") as cancel:
        monitor = TemperatureMonitor(window_size=20)

        # Create stream with some anomalies
        async def anomaly_stream():
            normal_count = 0
            async for reading in sensor_data_stream("SENSOR-001", interval=0.1, error_rate=0):
                normal_count += 1

                # Inject anomalies
                if normal_count % 30 == 0:
                    reading["temperature"] = reading["temperature"] + random.choice([-10, 10])
                    logger.info(f"Injected anomaly: {reading['temperature']}°C")

                yield reading

        # Process stream
        alert_count = 0
        async for reading in cancel.stream(anomaly_stream(), report_interval=50):
            alert = await monitor.process(reading)

            if alert:
                alert_count += 1
                print(f"\n  🚨 ALERT {alert_count}: {alert['type']}")
                print(f"     Temperature: {alert['value']}°C")
                print(f"     Average: {alert['average']}°C (±{alert['std_dev']}°C)")
                print(f"     Severity: {alert['severity']}")

        print(f"\n  Total alerts: {alert_count}")


async def main():
    """Run all stream processing examples."""
    print("Async Cancellation - Stream Processing Examples")
    print("=============================================")

    examples = [
        example_basic_stream_processing,
        example_multi_stream_merge,
        example_stream_transformation,
        example_chunked_processing,
        example_backpressure_handling,
        example_stateful_stream_processing,
    ]

    for example in examples:
        try:
            await example()
        except Exception as e:
            logger.error(f"Example failed: {e}", exc_info=True)
        print()


if __name__ == "__main__":
    anyio.run(main)
