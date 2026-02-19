"""Schema management API routes."""
from fastapi import APIRouter, HTTPException

from app.models.extracted_data_v2 import ExtractedDataV2
from app.utils.logger import logger

router = APIRouter(prefix="/schema", tags=["schema"])


@router.get("/extraction-schema")
async def get_extraction_schema():
    """Get the current extraction data schema."""
    try:
        schema = ExtractedDataV2.model_json_schema()
        return {"success": True, "data": schema}
    except Exception as e:
        logger.error(f"Get schema failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
