"""Race-safe automatic recalculation and hash-bound warning acceptance."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Iterable

from .models import WarningAcceptance


class CalculationState(str, Enum):
    MISSING_INPUT = "MISSING_INPUT"
    STALE = "STALE"
    RUNNING = "RUNNING"
    CURRENT = "CURRENT"
    NO_SOLUTION = "NO_SOLUTION"
    EXPERT_REVIEW = "EXPERT_REVIEW"


@dataclass(frozen=True)
class CalculationTicket:
    revision: int
    input_sha256: str


def _result_state(result: Any) -> CalculationState:
    status = getattr(result, "status", "")
    status_text = getattr(status, "value", status)
    if result is None or status_text in {"BLOCKED", "NO_SOLUTION", "REJECTED"}:
        return CalculationState.NO_SOLUTION
    if status_text in {"EXPERT_REVIEW", "EXPERT_REVIEW_REQUIRED", "VERIFIED_WITH_CONDITIONS"}:
        return CalculationState.EXPERT_REVIEW
    return CalculationState.CURRENT


class RecalculationCoordinator:
    """Coordinate UI snapshots, one background calculation and stale-result rejection.

    ``snapshot_factory`` is called only by scheduled/UI callbacks and must return
    ``(input_sha256, immutable_snapshot)``. ``submit`` accepts a zero-argument job
    and returns a Future-compatible object.
    """

    def __init__(
        self,
        snapshot_factory: Callable[[], tuple[str, Any]],
        calculate: Callable[[Any], Any],
        schedule: Callable[[int, Callable[[], None]], Any],
        cancel_schedule: Callable[[Any], None],
        submit: Callable[[Callable[[], Any]], Any],
        on_state: Callable[[CalculationState], None],
        on_result: Callable[[Any], None],
        delay_ms: int = 600,
    ) -> None:
        self.snapshot_factory = snapshot_factory
        self.calculate = calculate
        self.schedule = schedule
        self.cancel_schedule = cancel_schedule
        self.submit = submit
        self.on_state = on_state
        self.on_result = on_result
        self.delay_ms = delay_ms
        self.revision = 0
        self._scheduled = None
        self._future = None
        self._active_ticket: CalculationTicket | None = None
        self._closed = False

    def mark_changed(self) -> None:
        if self._closed:
            return
        self.revision += 1
        self._active_ticket = None
        if self._scheduled is not None:
            self.cancel_schedule(self._scheduled)
        self.on_state(CalculationState.STALE)
        self._scheduled = self.schedule(self.delay_ms, self.recalculate_now)

    def recalculate_now(self) -> CalculationTicket | None:
        if self._closed:
            return None
        if self._scheduled is not None:
            try:
                self.cancel_schedule(self._scheduled)
            except Exception:
                pass
            self._scheduled = None
        self.revision += 1
        try:
            input_sha256, snapshot = self.snapshot_factory()
        except (ValueError, TypeError):
            self._active_ticket = None
            self.on_state(CalculationState.MISSING_INPUT)
            return None
        ticket = CalculationTicket(self.revision, input_sha256)
        self._active_ticket = ticket
        self.on_state(CalculationState.RUNNING)
        future = self.submit(lambda: self.calculate(snapshot))
        self._future = future

        def completed(done) -> None:
            def apply() -> None:
                try:
                    result = done.result()
                except Exception as error:
                    if ticket == self._active_ticket:
                        self._active_ticket = None
                        self.on_state(CalculationState.EXPERT_REVIEW)
                        self.on_result(error)
                    return
                self.accept_completed(ticket, result)

            self.schedule(0, apply)

        future.add_done_callback(completed)
        return ticket

    def accept_completed(self, ticket: CalculationTicket, result: Any) -> bool:
        if self._closed or ticket != self._active_ticket or ticket.revision != self.revision:
            return False
        try:
            current_hash, _snapshot = self.snapshot_factory()
        except (ValueError, TypeError):
            self._active_ticket = None
            self.on_state(CalculationState.MISSING_INPUT)
            return False
        if current_hash != ticket.input_sha256:
            self._active_ticket = None
            self.on_state(CalculationState.STALE)
            return False
        self._active_ticket = None
        self.on_result(result)
        self.on_state(_result_state(result))
        return True

    def shutdown(self) -> None:
        self._closed = True
        self.revision += 1
        self._active_ticket = None
        if self._scheduled is not None:
            try:
                self.cancel_schedule(self._scheduled)
            except Exception:
                pass
            self._scheduled = None
        if self._future is not None:
            self._future.cancel()


def accept_warning(
    acceptances: Iterable[WarningAcceptance],
    warning_id: str,
    input_sha256: str,
    *,
    severity: str,
    comment: str = "",
) -> list[WarningAcceptance]:
    if severity.lower() != "warning":
        raise ValueError("Блокирующую ошибку нельзя игнорировать")
    if not warning_id.strip() or not input_sha256.strip():
        raise ValueError("Для принятия предупреждения нужны его ID и хеш исходных данных")
    filtered = [item for item in acceptances if item.warning_id != warning_id]
    filtered.append(WarningAcceptance(warning_id.strip(), input_sha256.strip(), comment.strip()))
    return filtered


def current_warning_acceptances(
    acceptances: Iterable[WarningAcceptance], input_sha256: str
) -> list[WarningAcceptance]:
    return [item for item in acceptances if item.input_sha256 == input_sha256]
