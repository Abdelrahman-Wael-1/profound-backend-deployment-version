"""
routes/courses.py
-----------------
All course-related endpoints consumed by:
  • CoursesListScreen   (Flutter)
  • CourseDetailsDashboard (Flutter)
  • ProfileScreen       (Flutter)
"""

import io
import pandas as pd
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models import CourseDB, StudentDB, PerformanceDB, ErrorAnalysisDB

router = APIRouter(tags=["courses"])


# ─────────────────────────────────────────────
#  Pydantic schemas (local to this router)
# ─────────────────────────────────────────────

class CourseCreate(BaseModel):
    user_id: int
    code: str
    name: str
    semester: str
    status: str = "active"
    schedule: str = "TBA"
    room: str = "TBA"
    department: Optional[str] = None


class CourseUpdate(BaseModel):
    code: str
    name: str
    semester: str
    status: str = "active"
    schedule: str = "TBA"
    room: str = "TBA"
    department: Optional[str] = None


class StudentCreate(BaseModel):
    student_id: str
    name: str
    department: Optional[str] = ""
    course_id: int


# ─────────────────────────────────────────────
#  Course CRUD
# ─────────────────────────────────────────────

@router.post("/courses")
def create_course(data: CourseCreate, db: Session = Depends(get_db)):
    """Create a new course for a professor (used in CoursesListScreen)."""
    course = CourseDB(
        user_id=data.user_id,
        code=data.code,
        name=data.name,
        semester=data.semester,
        status=data.status,
        schedule=data.schedule,
        room=data.room,
        department=data.department,
    )
    db.add(course)
    db.commit()
    db.refresh(course)
    return {"message": "Course created", "id": course.id}


@router.put("/courses/{course_id}")
def update_course(course_id: int, data: CourseUpdate, db: Session = Depends(get_db)):
    """Update an existing course (used in CoursesListScreen edit sheet)."""
    course = db.query(CourseDB).filter(CourseDB.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    course.code = data.code
    course.name = data.name
    course.semester = data.semester
    course.status = data.status
    course.schedule = data.schedule
    course.room = data.room
    course.department = data.department
    db.commit()
    return {"message": "Course updated"}


@router.delete("/courses/{course_id}")
def delete_course(course_id: int, db: Session = Depends(get_db)):
    """Delete a course and cascade-delete its students and lecture slots."""
    course = db.query(CourseDB).filter(CourseDB.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    # Manually delete all child records first (Neon/PostgreSQL enforces FK constraints)
    db.query(PerformanceDB).filter(PerformanceDB.course_id == course_id).delete(synchronize_session=False)
    db.query(ErrorAnalysisDB).filter(ErrorAnalysisDB.course_id == course_id).delete(synchronize_session=False)
    db.query(StudentDB).filter(StudentDB.course_id == course_id).delete(synchronize_session=False)
    db.query(LectureSlotDB).filter(LectureSlotDB.course_id == course_id).delete(synchronize_session=False)
    db.delete(course)
    db.commit()
    return {"message": "Course deleted"}


# ─────────────────────────────────────────────
#  Student management per course
# ─────────────────────────────────────────────

@router.get("/courses/{course_id}/students")
def get_students(course_id: int, db: Session = Depends(get_db)):
    """Return all students enrolled in a course (_StudentsSheet in Flutter)."""
    students = db.query(StudentDB).filter(StudentDB.course_id == course_id).all()
    return [
        {
            "id": s.id,
            "student_id": s.student_id,
            "name": s.name,
            "department": s.department,
        }
        for s in students
    ]


@router.post("/courses/{course_id}/students")
def add_student(course_id: int, data: StudentCreate, db: Session = Depends(get_db)):
    """Add a single student to a course (manual add dialog in Flutter)."""
    course = db.query(CourseDB).filter(CourseDB.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    # Prevent duplicate enrolment in same course
    existing = db.query(StudentDB).filter(
        StudentDB.student_id == data.student_id,
        StudentDB.course_id == course_id,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Student already enrolled in this course")

    student = StudentDB(
        student_id=data.student_id,
        name=data.name,
        department=data.department or "",
        course_id=course_id,
    )
    db.add(student)

    # Keep the headcount on the course row in sync
    course.students = db.query(func.count(StudentDB.id)).filter(
        StudentDB.course_id == course_id
    ).scalar() + 1

    db.commit()
    db.refresh(student)
    return {"message": "Student added", "id": student.id}


@router.delete("/courses/{course_id}/students/{student_id}")
def delete_student(course_id: int, student_id: int, db: Session = Depends(get_db)):
    """Remove a student from a course (swipe-to-delete in Flutter)."""
    student = db.query(StudentDB).filter(
        StudentDB.id == student_id,
        StudentDB.course_id == course_id,
    ).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    db.delete(student)

    # Update headcount
    course = db.query(CourseDB).filter(CourseDB.id == course_id).first()
    if course:
        count = db.query(func.count(StudentDB.id)).filter(
            StudentDB.course_id == course_id
        ).scalar()
        course.students = max(0, count - 1)

    db.commit()
    return {"message": "Student removed"}


@router.post("/courses/{course_id}/upload-students")
async def upload_students_excel(
    course_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Bulk-upload students from an Excel / CSV file.
    Required columns: student_id, name
    Optional column:  department
    """
    course = db.query(CourseDB).filter(CourseDB.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    content = await file.read()
    try:
        if file.filename.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(content))
        else:
            df = pd.read_excel(io.BytesIO(content), engine='openpyxl')
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not parse file: {e}")

    required = {"student_id", "name"}
    missing = required - set(df.columns.str.strip().str.lower())
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"File is missing required columns: {missing}. "
                   f"Expected: student_id, name (and optionally department).",
        )

    df.columns = df.columns.str.strip().str.lower()

    # Fetch existing student IDs for this course in one query
    existing_ids = {
        r[0] for r in db.query(StudentDB.student_id)
        .filter(StudentDB.course_id == course_id).all()
    }

    to_add = []
    skipped = 0
    for _, row in df.iterrows():
        sid = str(row["student_id"]).strip()
        if not sid:
            continue
        if sid in existing_ids:
            skipped += 1
            continue
        dept = str(row.get("department", "")).strip() if "department" in df.columns else ""
        to_add.append(StudentDB(
            student_id=sid,
            name=str(row["name"]).strip(),
            department=dept,
            course_id=course_id,
        ))
        existing_ids.add(sid)  # prevent duplicates within the file itself

    if to_add:
        db.bulk_save_objects(to_add)

    # Refresh headcount
    course.students = (
        db.query(func.count(StudentDB.id)).filter(StudentDB.course_id == course_id).scalar()
        + len(to_add)
    )

    db.commit()
    return {"message": f"Added {len(to_add)} student(s). Skipped {skipped} duplicate(s)."}


# ─────────────────────────────────────────────
#  Course Analytics  (CourseDetailsDashboard)
# ─────────────────────────────────────────────

@router.get("/course-analytics/{course_id}")
def get_course_analytics(course_id: int, db: Session = Depends(get_db)):
    """
    Returns the analytics payload consumed by CourseDetailsDashboard:
      average, at_risk, trend (list of weekly avg grades), distribution (A-F counts)
    Falls back to sensible empty values so the UI never crashes.
    """
    performances = (
        db.query(PerformanceDB)
        .filter(PerformanceDB.course_id == course_id)
        .all()
    )

    if not performances:
        return {
            "average": "N/A",
            "at_risk": 0,
            "trend": [0, 0, 0, 0, 0],
            "distribution": {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0},
        }

    grades = [p.grade for p in performances]
    avg = round(sum(grades) / len(grades), 1)
    at_risk = sum(1 for g in grades if g < 60)

    # Grade distribution
    dist = {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0}
    for g in grades:
        if g >= 90:
            dist["A"] += 1
        elif g >= 80:
            dist["B"] += 1
        elif g >= 70:
            dist["C"] += 1
        elif g >= 60:
            dist["D"] += 1
        else:
            dist["F"] += 1

    # Performance trend: chunk into 5 equal windows (simulates weekly trend)
    chunk_size = max(1, len(grades) // 5)
    trend = []
    for i in range(5):
        chunk = grades[i * chunk_size: (i + 1) * chunk_size]
        trend.append(round(sum(chunk) / len(chunk), 1) if chunk else avg)

    return {
        "average": f"{avg}%",
        "at_risk": at_risk,
        "trend": trend,
        "distribution": dist,
    }


# ─────────────────────────────────────────────
#  Profile Screen – bulk import course + students
# ─────────────────────────────────────────────

@router.post("/courses-with-students")
async def create_course_with_students(
    user_id: int = Form(...),
    code: str = Form(...),
    name: str = Form(...),
    semester: str = Form(...),
    schedule: str = Form("TBA"),
    room: str = Form("TBA"),
    department: Optional[str] = Form(None),
    status: str = Form("active"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    ProfileScreen uploads a single Excel/CSV that contains student rows
    together with course metadata sent as form fields.

    Required columns in file: student_id, name
    Optional column:           department
    """
    # 1. Create the course
    course = CourseDB(
        user_id=user_id,
        code=code,
        name=name,
        semester=semester,
        schedule=schedule,
        room=room,
        department=department,
        status=status,
    )
    db.add(course)
    db.flush()  # get course.id without committing

    # 2. Parse the student file
    content = await file.read()
    try:
        if file.filename.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(content))
        else:
            df = pd.read_excel(io.BytesIO(content), engine='openpyxl')
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Could not parse file: {e}")

    df.columns = df.columns.str.strip().str.lower()

    required = {"student_id", "name"}
    if not required.issubset(set(df.columns)):
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="File must contain at least 'student_id' and 'name' columns.",
        )

    added = 0
    for _, row in df.iterrows():
        sid = str(row["student_id"]).strip()
        if not sid:
            continue
        dept = str(row.get("department", "")).strip() if "department" in df.columns else ""
        db.add(StudentDB(
            student_id=sid,
            name=str(row["name"]).strip(),
            department=dept,
            course_id=course.id,
        ))
        added += 1

    course.students = added
    db.commit()
    return {"message": f"Course created with {added} students.", "course_id": course.id}


# ─────────────────────────────────────────────
#  Profile Screen – publications / projects / interests
# ─────────────────────────────────────────────
# These are simple inserts that the ProfileScreen hits via _submitData().
# They live here to keep main.py lean; you can also move them to a
# dedicated profile router if preferred.

from models import PublicationDB, ProjectDB, InterestDB
from schemas import PublicationCreate, ProjectCreate, InterestCreate


@router.post("/publications")
def add_publication(data: PublicationCreate, db: Session = Depends(get_db)):
    pub = PublicationDB(
        user_id=data.user_id,
        title=data.title,
        journal=data.journal,
        year=data.year,
        citations=data.citations,
    )
    db.add(pub)
    db.commit()
    return {"message": "Publication added"}


@router.post("/projects")
def add_project(data: ProjectCreate, db: Session = Depends(get_db)):
    proj = ProjectDB(
        user_id=data.user_id,
        title=data.title,
        team=data.team,
        year=data.year,
        status=data.status,
    )
    db.add(proj)
    db.commit()
    return {"message": "Project added"}


@router.post("/interests")
def add_interest(data: InterestCreate, db: Session = Depends(get_db)):
    interest = InterestDB(user_id=data.user_id, name=data.name)
    db.add(interest)
    db.commit()
    return {"message": "Interest added"}


# ─────────────────────────────────────────────
#  Profile Screen – profile/update alias
# ─────────────────────────────────────────────
# The profile screen calls PUT /profile/update/{id} but main.py only
# registers PUT /profile/{id}.  Register the alias here so both work.

from models import UserDB
from schemas import UserUpdate


@router.put("/profile/update/{user_id}")
def update_profile_alias(user_id: int, data: UserUpdate, db: Session = Depends(get_db)):
    """Alias for PUT /profile/{user_id} used by the profile edit sheet."""
    user = db.query(UserDB).filter(UserDB.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.full_name = data.full_name
    user.bio = data.bio
    user.department = data.department
    db.commit()
    return {"message": "Profile updated successfully"}

# ─────────────────────────────────────────────
#  Lecture Schedule (multiple slots per course)
# ─────────────────────────────────────────────

from models import LectureSlotDB

class LectureSlotCreate(BaseModel):
    day: str
    start_time: str
    end_time: str
    room: str


@router.get("/courses/{course_id}/schedule")
def get_schedule(course_id: int, db: Session = Depends(get_db)):
    slots = db.query(LectureSlotDB).filter(LectureSlotDB.course_id == course_id).all()
    return [
        {"id": s.id, "day": s.day, "start_time": s.start_time,
         "end_time": s.end_time, "room": s.room}
        for s in slots
    ]


@router.post("/courses/{course_id}/schedule")
def add_slot(course_id: int, data: LectureSlotCreate, db: Session = Depends(get_db)):
    course = db.query(CourseDB).filter(CourseDB.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    slot = LectureSlotDB(
        course_id=course_id,
        day=data.day,
        start_time=data.start_time,
        end_time=data.end_time,
        room=data.room,
    )
    db.add(slot)
    db.commit()
    db.refresh(slot)
    return {"message": "Slot added", "id": slot.id}


@router.put("/courses/{course_id}/schedule/{slot_id}")
def update_slot(course_id: int, slot_id: int, data: LectureSlotCreate, db: Session = Depends(get_db)):
    slot = db.query(LectureSlotDB).filter(
        LectureSlotDB.id == slot_id, LectureSlotDB.course_id == course_id
    ).first()
    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found")
    slot.day = data.day
    slot.start_time = data.start_time
    slot.end_time = data.end_time
    slot.room = data.room
    db.commit()
    return {"message": "Slot updated"}


@router.delete("/courses/{course_id}/schedule/{slot_id}")
def delete_slot(course_id: int, slot_id: int, db: Session = Depends(get_db)):
    slot = db.query(LectureSlotDB).filter(
        LectureSlotDB.id == slot_id, LectureSlotDB.course_id == course_id
    ).first()
    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found")
    db.delete(slot)
    db.commit()
    return {"message": "Slot deleted"}
