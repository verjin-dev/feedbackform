import os

# Set before any app import: app.core.database builds its engine from settings
# at import time, and the app refuses to start without an explicit URL.
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("SECRET_KEY", "test-only-signing-key")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.pool import StaticPool
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
    # StaticPool keeps every connection pointed at the same in-memory
    # database; without it each connection gets its own empty one.
    # check_same_thread is off because TestClient runs the app on another
    # thread than the test.
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )

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


@pytest.fixture
def client(session: Session) -> TestClient:
    """App wired to the test session, so requests and fixtures see one
    database."""
    from app.core.database import get_session
    from app.main import app

    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _reset_throttle():
    """The login throttle is process-global; without this, tests that generate
    failures would leak into later ones."""
    from app.core.throttle import login_throttle

    login_throttle._attempts.clear()
    yield
    login_throttle._attempts.clear()


ADMIN_PASSWORD = "conftest-admin-password"


@pytest.fixture
def admin_account(session: Session) -> Account:
    from app.core.security import hash_password

    account = Account(
        role=Role.admin,
        first_name="Root",
        last_name="Admin",
        email="root.admin@example.edu",
        password_hash=hash_password(ADMIN_PASSWORD),
    )
    session.add(account)
    session.commit()
    return account


@pytest.fixture
def admin_client(client: TestClient, admin_account: Account) -> TestClient:
    """A client already signed in as an administrator."""
    response = client.post(
        "/auth/login",
        json={"email": admin_account.email, "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200, response.text
    return client


@pytest.fixture
def student_client(client: TestClient, fixtures: dict, session: Session) -> TestClient:
    """A client signed in as a student, for checking that admin routes refuse."""
    from app.core.security import hash_password

    student = fixtures["student"]
    student.password_hash = hash_password(ADMIN_PASSWORD)
    session.commit()

    response = client.post(
        "/auth/login", json={"email": student.email, "password": ADMIN_PASSWORD}
    )
    assert response.status_code == 200, response.text
    return client


@pytest.fixture(autouse=True)
def outbox():
    """Every test gets a capturing mailer, so none can reach a real server and
    any of them can read what was sent."""
    from app.core.email import MemoryMailer, set_mailer

    mailer = MemoryMailer()
    set_mailer(mailer)
    yield mailer.outbox
    set_mailer(None)
