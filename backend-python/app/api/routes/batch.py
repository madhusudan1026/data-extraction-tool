"""Batch processing API routes (V2 era - depends on removed ExtractionJob model)."""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from app.schemas.batch import (
    BatchJobRequest,
    BatchJobCreateResponse,
    BatchJobResponse,
    BatchJobListResponse,
    BatchJobStartResponse,
    BatchJobCancelResponse,
    BatchJobRetryResponse,
)
from app.utils.logger import logger

# batch_service depends on ExtractionJob model which was removed in P0.
# Guard import so the app still starts; all batch endpoints return 501.
try:
    from app.services.batch_service import batch_service
except (ImportError, NameError):
    batch_service = None
    logger.warning("batch_service unavailable (ExtractionJob model removed). Batch endpoints disabled.")

router = APIRouter(prefix="/batch", tags=["batch"])


@router.post("/", response_model=BatchJobCreateResponse)
async def create_batch_job(request: BatchJobRequest):
    """Create a new batch extraction job."""
    if batch_service is None:
        raise HTTPException(status_code=501, detail="Batch processing is not available (legacy V2 feature)")
    try:
        items = [item.dict() for item in request.items]
        config = request.config.dict() if request.config else {}

        job = await batch_service.create_batch_job(
            items=items,
            job_name=request.job_name,
            job_description=request.job_description,
            config=config,
            tags=request.tags,
        )

        return BatchJobCreateResponse(data=BatchJobResponse.model_validate(job))
    except Exception as e:
        logger.error(f"Create batch job failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{job_id}/start", response_model=BatchJobStartResponse)
async def start_batch_job(job_id: str):
    """Start processing a batch job."""
    try:
        await batch_service.start_batch_job(job_id)
        return BatchJobStartResponse(job_id=job_id)
    except Exception as e:
        logger.error(f"Start batch job failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{job_id}/cancel", response_model=BatchJobCancelResponse)
async def cancel_batch_job(job_id: str):
    """Cancel a batch job."""
    try:
        await batch_service.cancel_batch_job(job_id)
        return BatchJobCancelResponse(job_id=job_id)
    except Exception as e:
        logger.error(f"Cancel batch job failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{job_id}/retry", response_model=BatchJobRetryResponse)
async def retry_failed_items(job_id: str):
    """Retry failed items in a batch job."""
    try:
        job = await batch_service.retry_failed_items(job_id)
        failed_count = len(job.get_failed_items())
        return BatchJobRetryResponse(job_id=job_id, retried_items=failed_count)
    except Exception as e:
        logger.error(f"Retry failed items failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{job_id}", response_model=BatchJobResponse)
async def get_batch_job(job_id: str):
    """Get batch job by ID."""
    try:
        job = await batch_service.get_batch_job(job_id)
        return BatchJobResponse.model_validate(job)
    except Exception as e:
        logger.error(f"Get batch job failed: {str(e)}")
        raise HTTPException(status_code=404, detail="Job not found")


@router.get("/")
async def list_batch_jobs(
    page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=100)
):
    """List batch jobs with pagination."""
    try:
        # Batch functionality uses the batch_service which manages its own storage
        return {
            "data": [],
            "pagination": {"total": 0, "page": page, "limit": limit, "pages": 0},
            "message": "Batch jobs are managed through the V4 extraction pipeline"
        }
    except Exception as e:
        logger.error(f"List batch jobs failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
