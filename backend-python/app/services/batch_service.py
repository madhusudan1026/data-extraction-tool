"""
Batch service for processing multiple extractions concurrently.
Manages batch job execution with concurrency control and error handling.
"""
from typing import List, Dict, Any, Optional
from datetime import datetime
import asyncio
import uuid

from app.core.config import settings
from app.core.exceptions import BatchProcessingError
from app.utils.logger import logger
from app.services.enhanced_extraction_service import enhanced_extraction_service


class BatchService:
    """Service for batch processing operations."""

    def __init__(self):
        self.max_batch_size = settings.BATCH_MAX_SIZE
        self.default_concurrency = settings.BATCH_CONCURRENCY

    async def create_batch_job(
        self,
        items: List[Dict[str, Any]],
        job_name: Optional[str] = None,
        job_description: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
    ) -> ExtractionJob:
        """
        Create a new batch extraction job.

        Args:
            items: List of items to process.
            job_name: Optional job name.
            job_description: Optional job description.
            config: Job configuration.
            tags: Optional tags.

        Returns:
            Created ExtractionJob.

        Raises:
            BatchProcessingError: If job creation fails.
        """
        try:
            if len(items) > self.max_batch_size:
                raise BatchProcessingError(
                    f"Batch size exceeds maximum of {self.max_batch_size}"
                )

            # Create job items
            job_items = []
            for i, item in enumerate(items):
                item_id = item.get("item_id") or f"item_{uuid.uuid4().hex[:8]}"
                job_items.append(
                    JobItem(
                        item_id=item_id,
                        source_type=item["source_type"],
                        source=item["source"],
                        status=JobItemStatus.PENDING,
                    )
                )

            # Create job
            job = ExtractionJob(
                job_name=job_name,
                job_description=job_description,
                items=job_items,
                config=config or {},
                tags=tags or [],
            )
            job.update_statistics()
            await job.insert()

            logger.info(f"Created batch job: {job.id} with {len(job_items)} items")
            return job

        except Exception as e:
            logger.error(f"Failed to create batch job: {str(e)}")
            raise BatchProcessingError(f"Failed to create batch job: {str(e)}")

    async def start_batch_job(self, job_id: str) -> ExtractionJob:
        """
        Start processing a batch job.

        Args:
            job_id: ID of the job to start.

        Returns:
            Updated ExtractionJob.

        Raises:
            BatchProcessingError: If job start fails.
        """
        try:
            job = await ExtractionJob.get(job_id)
            if not job:
                raise BatchProcessingError("Job not found")

            if job.status != JobStatus.PENDING:
                raise BatchProcessingError(f"Job is not in pending status: {job.status}")

            await job.start_job()
            logger.info(f"Started batch job: {job_id}")

            # Process job asynchronously
            asyncio.create_task(self._process_batch_job(job_id))

            return job

        except Exception as e:
            logger.error(f"Failed to start batch job: {str(e)}")
            raise BatchProcessingError(f"Failed to start batch job: {str(e)}")

    async def _process_batch_job(self, job_id: str):
        """
        Process batch job items with concurrency control.

        Args:
            job_id: ID of the job to process.
        """
        try:
            job = await ExtractionJob.get(job_id)
            if not job:
                logger.error(f"Job not found: {job_id}")
                return

            concurrency = job.config.concurrency or self.default_concurrency
            pending_items = job.get_pending_items()

            logger.info(
                f"Processing {len(pending_items)} items with concurrency={concurrency}"
            )

            # Create semaphore for concurrency control
            semaphore = asyncio.Semaphore(concurrency)

            # Process items
            tasks = [
                self._process_item(job_id, item, semaphore) for item in pending_items
            ]
            await asyncio.gather(*tasks, return_exceptions=True)

            # Complete job
            await job.reload()
            if job.has_pending_items():
                await job.fail_job("Some items remain pending")
            else:
                await job.complete_job()

            logger.info(f"Batch job completed: {job_id}")

        except Exception as e:
            logger.error(f"Batch job processing error: {str(e)}")
            try:
                job = await ExtractionJob.get(job_id)
                if job:
                    await job.fail_job(str(e))
            except:
                pass

    async def _process_item(
        self, job_id: str, item: JobItem, semaphore: asyncio.Semaphore
    ):
        """
        Process a single batch item.

        Args:
            job_id: Job ID.
            item: Item to process.
            semaphore: Concurrency semaphore.
        """
        async with semaphore:
            job = await ExtractionJob.get(job_id)
            if not job:
                return

            start_time = datetime.utcnow()

            try:
                # Update status to processing
                await job.update_item_status(item.item_id, JobItemStatus.PROCESSING)

                # Perform extraction
                result = await extraction_service.extract(
                    source_type=item.source_type,
                    source=item.source,
                    config=job.config.extraction_config,
                )

                # Calculate processing time
                processing_time_ms = int(
                    (datetime.utcnow() - start_time).total_seconds() * 1000
                )

                # Update status to completed
                await job.reload()
                await job.update_item_status(
                    item.item_id,
                    JobItemStatus.COMPLETED,
                    result_id=str(result.id),
                    processing_time_ms=processing_time_ms,
                )

                logger.info(f"Item {item.item_id} completed successfully")

            except Exception as e:
                logger.error(f"Item {item.item_id} failed: {str(e)}")

                # Check if we should retry
                await job.reload()
                current_item = job.get_item(item.item_id)
                if (
                    current_item
                    and job.config.retry_failed
                    and current_item.retry_count < job.config.max_retries
                ):
                    # Reset to pending for retry
                    await job.update_item_status(
                        item.item_id, JobItemStatus.PENDING, error=str(e)
                    )
                    current_item.retry_count += 1
                else:
                    # Mark as failed
                    await job.update_item_status(
                        item.item_id, JobItemStatus.FAILED, error=str(e)
                    )

                # Check if should stop on error
                if job.config.stop_on_error:
                    await job.fail_job(f"Stopped due to error in item {item.item_id}")

    async def get_batch_job(self, job_id: str) -> ExtractionJob:
        """
        Get batch job by ID.

        Args:
            job_id: Job ID.

        Returns:
            ExtractionJob.

        Raises:
            BatchProcessingError: If job not found.
        """
        job = await ExtractionJob.get(job_id)
        if not job:
            raise BatchProcessingError("Job not found")
        return job

    async def cancel_batch_job(self, job_id: str) -> ExtractionJob:
        """
        Cancel a batch job.

        Args:
            job_id: Job ID.

        Returns:
            Updated ExtractionJob.

        Raises:
            BatchProcessingError: If cancellation fails.
        """
        job = await self.get_batch_job(job_id)

        if job.status not in [JobStatus.PENDING, JobStatus.PROCESSING]:
            raise BatchProcessingError(f"Cannot cancel job with status: {job.status}")

        await job.cancel_job()
        logger.info(f"Cancelled batch job: {job_id}")
        return job

    async def retry_failed_items(self, job_id: str) -> ExtractionJob:
        """
        Retry failed items in a batch job.

        Args:
            job_id: Job ID.

        Returns:
            Updated ExtractionJob.

        Raises:
            BatchProcessingError: If retry fails.
        """
        job = await self.get_batch_job(job_id)

        failed_items = job.get_failed_items()
        if not failed_items:
            raise BatchProcessingError("No failed items to retry")

        # Reset failed items to pending
        for item in failed_items:
            await job.update_item_status(item.item_id, JobItemStatus.PENDING)

        # Restart job if completed
        if job.status == JobStatus.COMPLETED:
            await job.start_job()
            asyncio.create_task(self._process_batch_job(job_id))

        logger.info(f"Retrying {len(failed_items)} failed items in job: {job_id}")
        return job


# Global batch service instance
batch_service = BatchService()
