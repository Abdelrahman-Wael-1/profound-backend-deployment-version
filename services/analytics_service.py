from sqlalchemy.orm import Session
from models import PerformanceDB, CourseDB
from datetime import datetime, timedelta

def get_performance_distribution(db: Session, course_id: int = None, semester: str = None, days: int = None):
    query = db.query(PerformanceDB.grade)
    
    if course_id and course_id != 0:
        query = query.filter(PerformanceDB.course_id == course_id)
    
    if semester and semester != "All Semesters":
        query = query.join(CourseDB).filter(CourseDB.semester == semester)
    if days:
        cutoff = datetime.utcnow() - timedelta(days=days)
        query = query.filter(PerformanceDB.created_at >= cutoff)
        
    grades = [g[0] for g in query.all()]
    dist = {"Excellent (90-100)": 0, "Good (80-89)": 0, "Average (70-79)": 0, "At-Risk (<70)": 0}
    
    for g in grades:
        if g >= 90: dist["Excellent (90-100)"] += 1
        elif g >= 80: dist["Good (80-89)"] += 1
        elif g >= 70: dist["Average (70-79)"] += 1
        else: dist["At-Risk (<70)"] += 1
    return dist

def get_attendance_correlation_report(db: Session, course_id: int = None, semester: str = None, days: int = None):
    query = db.query(PerformanceDB.attendance, PerformanceDB.grade)
    
    if course_id and course_id != 0:
        query = query.filter(PerformanceDB.course_id == course_id)
    if semester and semester != "All Semesters":
        query = query.join(CourseDB).filter(CourseDB.semester == semester)
    if days:
        cutoff = datetime.utcnow() - timedelta(days=days)
        query = query.filter(PerformanceDB.created_at >= cutoff)
    
    data = query.all()
    if len(data) < 2:
        return {"stats": {"r_squared": 0, "label": "N/A"}, "insight": "No data", "points": []}

    x, y = [d.attendance for d in data], [d.grade for d in data]
    n = len(data)

    sum_x, sum_y = sum(x), sum(y)
    sum_xy = sum(i*j for i, j in zip(x, y))
    sum_x_sq, sum_y_sq = sum(i**2 for i in x), sum(i**2 for i in y)

    num = (n * sum_xy) - (sum_x * sum_y)
    den = ((n * sum_x_sq - sum_x**2) * (n * sum_y_sq - sum_y**2))**0.5
    r_sq = (num / den)**2 if den != 0 else 0
    
    slope = num / (n * sum_x_sq - sum_x**2) if (n * sum_x_sq - sum_x**2) != 0 else 0
    impact = round(slope * 10, 1)
    
    return {
        "stats": {"r_squared": round(r_sq, 2), "label": f"R² = {round(r_sq, 2)} ({'Strong' if r_sq > 0.7 else 'Moderate' if r_sq > 0.4 else 'Weak'})"},
        "insight": f"Each 10% attendance ↑ = {impact}% grade ↑",
        "points": [{"attendance": d.attendance, "grade": d.grade} for d in data]
    }
