import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.models import (
    AcademicTerm,
    Account,
    Base,
    ClassGroup,
    Criterion,
    Question,
    Role,
    Subject,
    TeachingAssignment,
    TermStatus,
)


@pytest.fixture
def engine():
    eng = create_engine("sqlite://", future=True)

    @event.listens_for(eng, "connect")
    def _fk_on(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine) -> Session:
    with Session(engine) as s:
        yield s


@pytest.fixture
def fixtures(session: Session) -> dict:
    """A minimal but complete term: one class, one subject, one faculty
    member, one student, one assignment and two questions."""
    term = AcademicTerm(
        year="2025-2026", semester=1, status=TermStatus.open, is_current=True
    )
    klass = ClassGroup(curriculum="B.E. CSE", level="III", section="A")
    subject = Subject(code="CS3401", name="Algorithms")
    session.add_all([term, klass, subject])
    session.flush()

    faculty = Account(
        role=Role.faculty,
        school_id="F1001",
        first_name="Asha",
        last_name="Raman",
        email="asha.raman@example.edu",
        password_hash="argon2-placeholder",
    )
    student = Account(
        role=Role.student,
        school_id="S2201",
        first_name="Karthik",
        last_name="Iyer",
        email="karthik.iyer@example.edu",
        password_hash="argon2-placeholder",
        class_group_id=klass.id,
    )
    criterion = Criterion(name="Subject knowledge", position=1)
    session.add_all([faculty, student, criterion])
    session.flush()

    assignment = TeachingAssignment(
        term_id=term.id,
        faculty_id=faculty.id,
        class_group_id=klass.id,
        subject_id=subject.id,
    )
    questions = [
        Question(
            term_id=term.id,
            criterion_id=criterion.id,
            text="Explains concepts clearly.",
            position=1,
        ),
        Question(
            term_id=term.id,
            criterion_id=criterion.id,
            text="Answers questions thoroughly.",
            position=2,
        ),
    ]
    session.add(assignment)
    session.add_all(questions)
    session.commit()

    return {
        "term": term,
        "class_group": klass,
        "subject": subject,
        "faculty": faculty,
        "student": student,
        "criterion": criterion,
        "assignment": assignment,
        "questions": questions,
    }
