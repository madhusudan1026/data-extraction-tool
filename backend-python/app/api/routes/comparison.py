"""Comparison API routes."""
from fastapi import APIRouter, HTTPException, Query

from app.schemas.comparison import (
    ComparisonCreateRequest,
    ComparisonResponse,
    ComparisonListResponse,
    ComparisonAnalysisResponse,
    ComparisonDeleteResponse,
)
from app.services.comparison_service import comparison_service
from app.models.comparison import Comparison
from app.utils.logger import logger

router = APIRouter(prefix="/comparison", tags=["comparison"])


@router.post("/", response_model=ComparisonResponse)
async def create_comparison(request: ComparisonCreateRequest):
    """Create a new card comparison."""
    try:
        comparison = await comparison_service.create_comparison(
            comparison_name=request.comparison_name,
            card_ids=request.card_ids,
            description=request.description,
            criteria=request.criteria.dict() if request.criteria else None,
            is_public=request.is_public,
            tags=request.tags,
        )
        return ComparisonResponse.model_validate(comparison)
    except Exception as e:
        logger.error(f"Create comparison failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{comparison_id}/analyze", response_model=ComparisonAnalysisResponse)
async def analyze_comparison(comparison_id: str):
    """Analyze a comparison and generate results."""
    try:
        result = await comparison_service.analyze_comparison(comparison_id)
        return ComparisonAnalysisResponse(comparison_id=comparison_id, results=result)
    except Exception as e:
        logger.error(f"Analyze comparison failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{comparison_id}", response_model=ComparisonResponse)
async def get_comparison(comparison_id: str):
    """Get comparison by ID."""
    try:
        comparison = await comparison_service.get_comparison(comparison_id)
        return ComparisonResponse.model_validate(comparison)
    except Exception as e:
        logger.error(f"Get comparison failed: {str(e)}")
        raise HTTPException(status_code=404, detail="Comparison not found")


@router.delete("/{comparison_id}", response_model=ComparisonDeleteResponse)
async def delete_comparison(comparison_id: str):
    """Delete a comparison."""
    try:
        await comparison_service.delete_comparison(comparison_id)
        return ComparisonDeleteResponse()
    except Exception as e:
        logger.error(f"Delete comparison failed: {str(e)}")
        raise HTTPException(status_code=404, detail="Comparison not found")


@router.get("/", response_model=ComparisonListResponse)
async def list_comparisons(
    page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=100)
):
    """List comparisons with pagination."""
    try:
        skip = (page - 1) * limit
        comparisons = await Comparison.find().skip(skip).limit(limit).to_list()
        total = await Comparison.find().count()

        return ComparisonListResponse(
            data=[ComparisonResponse.model_validate(c) for c in comparisons],
            pagination={"total": total, "page": page, "limit": limit, "pages": (total + limit - 1) // limit},
        )
    except Exception as e:
        logger.error(f"List comparisons failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
