"""
Integration tests for the async cancelation system.
"""

import anyio
import pytest

from hother.cancelable import Cancelable, CancelationReason, CancelationToken, OperationRegistry, cancelable


class TestIntegration:
    """Integration tests covering complete workflows."""

    @pytest.mark.anyio
    async def test_http_download_simulation(self):
        """Test simulated HTTP download with cancelation."""
        downloaded_chunks = []

        async def simulate_download(url: str, cancelable: Cancelable):
            """Simulate downloading a file in chunks."""
            total_chunks = 20

            for i in range(total_chunks):
                await anyio.sleep(0.05)  # Simulate network delay
                chunk = f"chunk_{i}_from_{url}"
                downloaded_chunks.append(chunk)

                if (i + 1) % 5 == 0:
                    await cancelable.report_progress(f"Downloaded {i + 1}/{total_chunks} chunks", {"progress": (i + 1) / total_chunks * 100})

                # Check for cancelation
                await cancelable._token.check_async()

            return len(downloaded_chunks)

        # Test successful download
        downloaded_chunks.clear()
        async with Cancelable(name="download_test") as cancel:
            result = await simulate_download("http://example.com/file.zip", cancel)
            assert result == 20

        # Test timeout during download
        downloaded_chunks.clear()
        with pytest.raises(anyio.get_cancelled_exc_class()):
            async with Cancelable.with_timeout(0.3, name="timeout_download") as cancel:
                await simulate_download("http://example.com/large.zip", cancel)

        # Should have partial download
        assert 0 < len(downloaded_chunks) < 20

    @pytest.mark.anyio
    async def test_database_transaction_simulation(self):
        """Test simulated database operations with cancelation."""

        class MockDatabase:
            def __init__(self):
                self.records = []
                self.in_transaction = False
                self.committed = False

            async def begin(self):
                self.in_transaction = True
                self.committed = False

            async def insert(self, record):
                if not self.in_transaction:
                    raise RuntimeError("Not in transaction")
                self.records.append(record)

            async def commit(self):
                if not self.in_transaction:
                    raise RuntimeError("Not in transaction")
                self.committed = True
                self.in_transaction = False

            async def rollback(self):
                if self.in_transaction:
                    self.records.clear()
                    self.in_transaction = False

        db = MockDatabase()

        @cancelable(name="db_operation")
        async def insert_records(count: int, db: MockDatabase, cancelable: Cancelable = None):
            """Insert records with cancelation support."""
            await db.begin()

            try:
                for i in range(count):
                    await db.insert(f"record_{i}")

                    if i % 10 == 0:
                        await cancelable.report_progress(f"Inserted {i}/{count} records")

                    # Simulate slow operation
                    await anyio.sleep(0.01)

                await db.commit()
                return len(db.records)

            except anyio.get_cancelled_exc_class():
                await db.rollback()
                raise

        # Test successful transaction
        result = await insert_records(20, db)
        assert result == 20
        assert db.committed
        assert len(db.records) == 20

        # Test cancelled transaction
        db.records.clear()
        token = CancelationToken()

        async def cancel_after_delay():
            await anyio.sleep(0.1)
            await token.cancel()

        async with anyio.create_task_group() as tg:
            tg.start_soon(cancel_after_delay)

            with pytest.raises(anyio.get_cancelled_exc_class()):
                async with Cancelable.with_token(token):
                    await insert_records(50, db)

        # Transaction should be rolled back
        assert len(db.records) == 0
        assert not db.in_transaction

    @pytest.mark.anyio
    async def test_multi_stage_pipeline(self):
        """Test multi-stage data processing pipeline."""

        async def stage1_fetch(cancelable: Cancelable) -> list:
            """Fetch data from source."""
            await cancelable.report_progress("Fetching data")
            data = []

            for i in range(10):
                await anyio.sleep(0.05)
                data.append({"id": i, "value": i * 10})
                await cancelable._token.check_async()

            await cancelable.report_progress(f"Fetched {len(data)} items")
            return data

        async def stage2_process(data: list, cancelable: Cancelable) -> list:
            """Process the data."""
            await cancelable.report_progress("Processing data")
            processed = []

            for item in data:
                await anyio.sleep(0.02)
                processed.append({**item, "processed": True, "score": item["value"] * 2})
                await cancelable._token.check_async()

            await cancelable.report_progress(f"Processed {len(processed)} items")
            return processed

        async def stage3_save(data: list, cancelable: Cancelable) -> int:
            """Save the processed data."""
            await cancelable.report_progress("Saving data")
            saved_count = 0

            for item in data:
                await anyio.sleep(0.01)
                # Simulate save
                saved_count += 1
                await cancelable._token.check_async()

            await cancelable.report_progress(f"Saved {saved_count} items")
            return saved_count

        # Test complete pipeline
        async with Cancelable(name="pipeline") as cancel:
            # Stage 1
            raw_data = await stage1_fetch(cancel)
            assert len(raw_data) == 10

            # Stage 2
            processed_data = await stage2_process(raw_data, cancel)
            assert len(processed_data) == 10
            assert all(item["processed"] for item in processed_data)

            # Stage 3
            saved = await stage3_save(processed_data, cancel)
            assert saved == 10

        # Test pipeline cancelation at different stages
        for cancel_after in [0.3, 0.8, 1.2]:
            token = CancelationToken()

            async def cancel_pipeline():
                await anyio.sleep(cancel_after)
                await token.cancel()

            stage_reached = 0

            async with anyio.create_task_group() as tg:
                tg.start_soon(cancel_pipeline)

                try:
                    async with Cancelable.with_token(token, name="pipeline_cancel") as cancel:
                        raw_data = await stage1_fetch(cancel)
                        stage_reached = 1

                        processed_data = await stage2_process(raw_data, cancel)
                        stage_reached = 2

                        saved = await stage3_save(processed_data, cancel)
                        stage_reached = 3

                except anyio.get_cancelled_exc_class():
                    pass

            # Verify cancelation happened at expected stage
            if cancel_after < 0.6:
                assert stage_reached <= 1
            elif cancel_after < 1.0:
                assert stage_reached <= 2
            else:
                assert stage_reached <= 3

    @pytest.mark.anyio
    async def test_recursive_cancelation(self):
        """Test recursive operation cancelation."""
        execution_order = []

        async def recursive_operation(depth: int, cancelable: Cancelable):
            """Recursive operation that creates child operations."""
            execution_order.append(f"start_{depth}")

            if depth > 0:
                # Create child operation
                async with Cancelable(name=f"level_{depth}", parent=cancelable) as child:
                    await anyio.sleep(0.05)
                    await recursive_operation(depth - 1, child)

            execution_order.append(f"end_{depth}")

        # Test successful completion
        execution_order.clear()
        async with Cancelable(name="root") as root:
            await recursive_operation(3, root)

        # Verify execution order
        assert execution_order == ["start_3", "start_2", "start_1", "start_0", "end_0", "end_1", "end_2", "end_3"]

        # Test cancelation propagation
        execution_order.clear()
        root_cancel = Cancelable(name="root")

        async def cancel_root():
            await anyio.sleep(0.15)
            await root_cancel.cancel()

        async with anyio.create_task_group() as tg:
            tg.start_soon(cancel_root)

            try:
                async with root_cancel:
                    await recursive_operation(5, root_cancel)
            except anyio.get_cancelled_exc_class():
                pass

        # Should have started some operations but not completed all
        start_count = sum(1 for x in execution_order if x.startswith("start_"))
        end_count = sum(1 for x in execution_order if x.startswith("end_"))
        assert start_count > end_count

    @pytest.mark.anyio
    async def test_real_world_scenario(self):
        """Test a real-world scenario with multiple features."""

        # Simulate a web scraping operation
        class WebScraper:
            def __init__(self):
                self.pages_scraped = 0
                self.data_extracted = []
                self.errors = []

            @cancelable(register_globally=True)
            async def scrape_site(self, base_url: str, page_count: int, cancelable: Cancelable = None):
                """Scrape multiple pages from a site."""
                for page_num in range(1, page_count + 1):
                    page_url = f"{base_url}/page/{page_num}"

                    try:
                        # Scrape with timeout per page
                        async with cancelable.shield() as shielded:
                            data = await self._scrape_page(page_url, shielded)
                            self.data_extracted.extend(data)
                            self.pages_scraped += 1

                        await cancelable.report_progress(
                            f"Scraped page {page_num}/{page_count}",
                            {
                                "pages_scraped": self.pages_scraped,
                                "items_extracted": len(self.data_extracted),
                            },
                        )

                    except Exception as e:
                        self.errors.append((page_url, str(e)))
                        await cancelable.report_progress(f"Error scraping {page_url}: {e}")

                return {
                    "pages_scraped": self.pages_scraped,
                    "items_extracted": len(self.data_extracted),
                    "errors": len(self.errors),
                }

            async def _scrape_page(self, url: str, cancelable: Cancelable) -> list:
                """Scrape a single page."""
                # Simulate page fetch
                await anyio.sleep(0.1)

                # Simulate data extraction
                items = []
                for i in range(5):
                    await anyio.sleep(0.02)
                    items.append({"url": url, "item_id": i, "data": f"data_{i}"})

                return items

        # Test the scraper
        scraper = WebScraper()
        registry = OperationRegistry.get_instance()

        # Run scraping with monitoring
        result = await scraper.scrape_site("http://example.com", 5)

        assert result["pages_scraped"] == 5
        assert result["items_extracted"] == 25
        assert result["errors"] == 0

        # Test with cancelation
        scraper2 = WebScraper()
        token = CancelationToken()

        async def monitor_and_cancel():
            """Monitor progress and cancel if taking too long."""
            await anyio.sleep(0.3)

            # Check active operations
            ops = await registry.list_operations()
            for op in ops:
                if "scrape_site" in op.name and op.duration_seconds > 0.25:
                    await token.cancel(CancelationReason.TIMEOUT, "Scraping taking too long")

        async with anyio.create_task_group() as tg:
            tg.start_soon(monitor_and_cancel)

            try:
                async with Cancelable.with_token(token):
                    result = await scraper2.scrape_site("http://slow-site.com", 20)
            except anyio.get_cancelled_exc_class():
                pass

        # Should have scraped some pages before cancelation
        assert 0 < scraper2.pages_scraped < 20
        assert len(scraper2.data_extracted) > 0
