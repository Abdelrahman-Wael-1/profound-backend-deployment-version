from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from services.ai_lecture_generation_service import generate_lecture_json
from services.pptx_service import create_pptx
from schemas import LectureRequest

router = APIRouter(prefix="/api", tags=["Lecture"])

@router.post("/generate-lecture")
async def generate_lecture(data: LectureRequest):
    return generate_lecture_json(data)

@router.post("/export-pptx")
async def export_pptx(data: dict):
    file_stream = create_pptx(data)
    return StreamingResponse(
        file_stream,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": "attachment; filename=lecture.pptx"}
    )