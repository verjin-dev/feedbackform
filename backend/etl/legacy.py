"""Reading the legacy PHP database.

Works against MySQL (mysql+pymysql://...) for the real migration and against
SQLite for the tests, because every statement here is plain SQL over tables
that carry no constraints, no foreign keys and no indexes worth planning
around.

Nothing in this module writes. Reading production is safe.
"""

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

LEGACY_TABLES = (
    "academic_list",
    "class_list",
    "subject_list",
    "criteria_list",
    "question_list",
    "users",
    "faculty_list",
    "student_list",
    "restriction_list",
    "evaluation_list",
    "evaluation_answers",
)


class LegacyReader:
    def __init__(self, url: str) -> None:
        self.url = url
        self.engine: Engine = create_engine(url)

    def rows(self, table: str) -> list[dict[str, Any]]:
        if table not in LEGACY_TABLES:
            raise ValueError(f"Not a legacy table: {table}")
        with self.engine.connect() as connection:
            result = connection.execute(text(f"SELECT * FROM {table}"))
            return [dict(row) for row in result.mappings()]

    def missing_tables(self) -> list[str]:
        """The dead task module referenced tables that never existed. Anything
        genuinely missing here is a real problem, so it is checked up front
        rather than discovered halfway through a migration."""
        missing = []
        with self.engine.connect() as connection:
            for table in LEGACY_TABLES:
                try:
                    connection.execute(text(f"SELECT 1 FROM {table} LIMIT 1"))
                except Exception:  # noqa: BLE001 - dialects differ; absence is what matters
                    missing.append(table)
        return missing

    def close(self) -> None:
        self.engine.dispose()


# --- Findings --------------------------------------------------------------

BLOCKER = "blocker"
WARNING = "warning"
NOTE = "note"


@dataclass
class Finding:
    """One thing about the legacy data that the new schema will not accept, or
    that changes meaning on the way across."""

    level: str
    code: str
    message: str
    rows: list[Any] = field(default_factory=list)

    def __str__(self) -> str:
        suffix = ""
        if self.rows:
            shown = ", ".join(str(row) for row in self.rows[:8])
            more = f" (+{len(self.rows) - 8} more)" if len(self.rows) > 8 else ""
            suffix = f"  [{shown}{more}]"
        return f"{self.level.upper():8} {self.code}: {self.message}{suffix}"
