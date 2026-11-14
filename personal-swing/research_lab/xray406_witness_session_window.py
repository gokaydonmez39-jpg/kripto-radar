"""Resolve XNAS close+45 and Witness lifetime for offline slot planning."""
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from xray406_witness_acceptance import require, utc

FRESHNESS = timedelta(minutes=15)
AFTER_CLOSE = timedelta(minutes=45)


@dataclass(frozen=True)
class Window:
    session: str
    opens: datetime
    closes: datetime
    cutoff: datetime

    def publication_deadline(self, generated):
        generated = utc(generated)
        require(self.opens <= generated < self.cutoff, "WITNESS_OUTSIDE_XNAS_WINDOW")
        return min(self.cutoff, generated + FRESHNESS)


def window(day, calendar=None):
    require(type(day) is str, "INVALID_XNAS_DATE")
    try:
        parsed = date.fromisoformat(day)
    except ValueError:
        require(False, "INVALID_XNAS_DATE")
    require(parsed.isoformat() == day, "INVALID_XNAS_DATE")
    if calendar is None:
        import exchange_calendars as xc
        calendar = xc.get_calendar("XNAS")
    require(calendar.is_session(day), "NOT_XNAS_SESSION")
    opens = calendar.session_open(day).to_pydatetime().astimezone(timezone.utc)
    closes = calendar.session_close(day).to_pydatetime().astimezone(timezone.utc)
    require(opens < closes, "XNAS_WINDOW_INVALID")
    return Window(day, opens, closes, closes + AFTER_CLOSE)


def pick_latest_safe_slot(w, candidates, required_budget):
    """Slot is only a target, never evidence a runner met the deadline."""
    require(isinstance(required_budget, timedelta)
            and timedelta(0) < required_budget < FRESHNESS, "INVALID_SLOT_BUDGET")
    valid = set()
    for t in candidates:
        t = utc(t)
        if w.closes <= t < w.cutoff and t + required_budget < w.publication_deadline(t):
            valid.add(t)
    return max(valid, default=None)
