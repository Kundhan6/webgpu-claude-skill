"""Structured result/warning objects shared across core and bl. No bpy import.

§3 rule 10: a stage that cannot guarantee a correct result reports and
stops — it never produces a half-built rig. StageResult is the shared
vocabulary for that: `ok` flips False the moment anything calls .error()
or .critical(), and callers check it before proceeding.
"""
from dataclasses import dataclass, field
from enum import Enum


class Severity(Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class Notice:
    message: str
    severity: Severity = Severity.WARNING
    code: str = ""

    def __str__(self) -> str:
        return f"[{self.severity.value}] {self.message}"


@dataclass
class StageResult:
    """Outcome of one Crash Forge stage (probe, reset, prep, ...)."""

    ok: bool = True
    warnings: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    data: dict = field(default_factory=dict)

    def info(self, message: str, code: str = "") -> None:
        self.warnings.append(Notice(message, Severity.INFO, code))

    def warn(self, message: str, code: str = "") -> None:
        self.warnings.append(Notice(message, Severity.WARNING, code))

    def error(self, message: str, code: str = "") -> None:
        self.ok = False
        self.errors.append(Notice(message, Severity.ERROR, code))

    def critical(self, message: str, code: str = "") -> None:
        self.ok = False
        self.errors.append(Notice(message, Severity.CRITICAL, code))

    def as_lines(self) -> list:
        return [str(n) for n in (*self.errors, *self.warnings)]
