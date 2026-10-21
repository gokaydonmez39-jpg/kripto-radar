"""Strict per-process pacing of personal Alpaca SIP historical HTTP requests.

Alpaca Basic historical data is rate limited per account; a delay once per
symbol batch is insufficient for paginated requests. 0.70s/page is at most
86 page attempts per sliding 60 seconds from this Python process. Distinct
GitHub workflows still require separate account-level concurrency controls.
This does not attest to data rights, market quality, or PRIMARY/AL authority.
"""
from __future__ import annotations

import math
import time
from typing import Callable

MIN_INTERVAL_SECONDS = 0.70


class SipRequestPacer:
    def __init__(
        self,
        *,
        interval: float = MIN_INTERVAL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ):
        if (
            isinstance(interval, bool)
            or not isinstance(interval, (float, int))
            or not math.isfinite(interval)
            or interval < 0.65
        ):
            raise ValueError("ALPACA_SIP_PACE_INTERVAL_TOO_FAST_OR_INVALID")
        self.interval = float(interval)
        self.clock = clock
        self.sleeper = sleeper
        self.last_request_at: float | None = None
        # Number of paced outbound HTTP attempts in this process, never vendor data.
        self.request_attempts: int = 0

    def pace(self) -> None:
        now = float(self.clock())
        if not math.isfinite(now):
            raise ValueError("ALPACA_SIP_MONOTONIC_CLOCK_INVALID")
        if self.last_request_at is not None:
            if now < self.last_request_at:
                raise ValueError("ALPACA_SIP_MONOTONIC_CLOCK_REGRESSION")
            delay = self.last_request_at + self.interval - now
            if delay > 0:
                self.sleeper(delay)
                now = float(self.clock())
                if not math.isfinite(now) or now < self.last_request_at + self.interval - 1e-8:
                    raise ValueError("ALPACA_SIP_PACE_SLEEP_UNTRUSTWORTHY")
        self.last_request_at = now
        self.request_attempts += 1


PACER = SipRequestPacer()
