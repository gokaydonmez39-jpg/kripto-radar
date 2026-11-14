"""Run one checked Official Witness publication with injected ref transport.

Transport must enforce atomic compare-and-swap (expected old ref, fast-forward
only). No credentials, network calls or default production destination live
here. Callers must independently authenticate the transport and observation.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from xray406_witness_acceptance import MainReceipt, Rejected, check_acceptance, utc
from xray406_witness_handoff import CheckSource, RunReceipt, plan, staging_ref


class Indeterminate(RuntimeError):
    """A write may have occurred. Reconcile read-only. Never retry blindly."""


class Transport(Protocol):
    def head(self, ref: str) -> str: ...
    def publish_once(self, expected: str, candidate: str) -> bool: ...
    def read_target(self, candidate: str) -> MainReceipt: ...


@dataclass(frozen=True)
class PublishResult:
    candidate: str
    observed_at: datetime
    guard_blob: str
    ledger_blob: str


def publish(root, base: str, candidate: str, run: RunReceipt,
            source: CheckSource, transport: Transport, clock,
            cutoff: datetime) -> PublishResult:
    # Read target last, then rely on atomic lease at the actual write.
    stage, target = transport.head(staging_ref(candidate)), transport.head("target")
    decision = plan(root, base, candidate, run, source, stage, target, clock(), cutoff)
    checked_at = utc(clock())
    if not source.check.finished_at <= checked_at < decision.latest_observed_at:
        raise Rejected("PUBLISH_WINDOW_CLOSED")
    try:
        accepted = transport.publish_once(decision.expected, decision.candidate)
    except Exception as exc:
        raise Indeterminate("WRITE_OUTCOME_UNKNOWN_DO_NOT_RETRY") from exc
    if accepted is False:
        raise Rejected("LEASE_REJECTED_NO_RETRY")
    if accepted is not True:
        raise Indeterminate("WRITE_ACK_UNKNOWN_DO_NOT_RETRY")
    try:
        receipt = transport.read_target(decision.candidate)
        check_acceptance(root, base, candidate, source.check, receipt, cutoff)
        if receipt.observed_at > decision.latest_observed_at:
            raise Rejected("PUBLISH_WINDOW_CLOSED")
    except Exception as exc:
        raise Indeterminate("WRITE_ACCEPTED_READBACK_UNPROVEN_DO_NOT_RETRY") from exc
    return PublishResult(candidate, receipt.observed_at, receipt.guard_blob, receipt.ledger_blob)
