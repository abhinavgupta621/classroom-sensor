"""The class roster, and the consent flags that gate every biometric step.

Roster CSV columns (header row required):
    person_id, name, role, face_consent, voice_consent
role is "student" or "instructor". Consent columns take yes/no (also true/false, 1/0).

Consent is checked twice: when someone is enrolled, and again every time a session is
processed, so a student who withdraws consent drops out of the next run even if their
enrollment files are still on disk (run `purge-person` to delete those too).
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

YES = {"yes", "y", "true", "1"}
NO = {"no", "n", "false", "0", ""}


@dataclass(frozen=True)
class Person:
    person_id: str
    name: str
    role: str
    face_consent: bool
    voice_consent: bool

    @property
    def is_instructor(self) -> bool:
        return self.role == "instructor"


def _flag(value: str, column: str, row: int) -> bool:
    v = (value or "").strip().lower()
    if v in YES:
        return True
    if v in NO:
        return False
    raise ValueError(f"roster row {row}: {column} must be yes or no, got {value!r}")


def load_roster(path: str | Path) -> dict[str, Person]:
    people: dict[str, Person] = {}
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        need = {"person_id", "name", "role", "face_consent", "voice_consent"}
        missing = need - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"roster is missing columns: {', '.join(sorted(missing))}")
        for i, row in enumerate(reader, start=2):
            pid = row["person_id"].strip()
            if not pid:
                raise ValueError(f"roster row {i}: empty person_id")
            if pid in people:
                raise ValueError(f"roster row {i}: duplicate person_id {pid}")
            role = row["role"].strip().lower() or "student"
            if role not in {"student", "instructor"}:
                raise ValueError(f"roster row {i}: role must be student or instructor")
            people[pid] = Person(
                person_id=pid,
                name=row["name"].strip(),
                role=role,
                face_consent=_flag(row["face_consent"], "face_consent", i),
                voice_consent=_flag(row["voice_consent"], "voice_consent", i),
            )
    return people
