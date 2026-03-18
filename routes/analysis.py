from fastapi import APIRouter, Depends, HTTPException , Query
from sqlalchemy.orm import Session
from database import get_db
from services import analytics_service

router = APIRouter(prefix="/analysis", tags=["Analysis"])

@router.get("/performance")
def get_performance(course_id: int = None, semester: str = None, days: int = None, db: Session = Depends(get_db)):
    return analytics_service.get_performance_distribution(db, course_id, semester, days)

@router.get("/correlation")
def get_correlation(course_id: int = None, semester: str = None, days: int = None, db: Session = Depends(get_db)):
    return analytics_service.get_attendance_correlation_report(db, course_id, semester, days)

