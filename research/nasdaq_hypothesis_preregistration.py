"""NASDAQ scientific hypothesis preregistration — original zero-dependency research gate.
No code loading, market access, agent execution, orders, AL, notifications, state writes.
"""
from __future__ import annotations
from datetime import date
import hashlib
import json

class HypothesisBlocked(ValueError):
    pass

def _day(s: str) -> date:
    if type(s) is not str:
        raise HypothesisBlocked("DATE_REQUIRED")
    try:
        d=date.fromisoformat(s)
    except (ValueError,TypeError):
        raise HypothesisBlocked("BAD_DATE") from None
    if d.isoformat()!=s:
        raise HypothesisBlocked("NON_CANONICAL_DATE")
    return d

def register(spec: dict) -> str:
    """Return immutable fingerprint; static research spec, not a trained AI system."""
    if not isinstance(spec,dict) or set(spec)!={"id","asof","dev_end","holdback_start",
       "holdback_end","wf_start","wf_end","final_holdout_start","universe_asof",
       "universe_source","dataset_sha256","model_sha256","n_trials"}:
        raise HypothesisBlocked("RESEARCH_SPEC_SCHEMA_DRIFT")
    for k in ("id","universe_source"):
        if type(spec[k]) is not str or not spec[k].strip():
            raise HypothesisBlocked("RESEARCH_ID_OR_UNIVERSE_SOURCE_MISSING")
    if not all(type(spec[k]) is str and len(spec[k])==64 and all(c in "0123456789abcdef" for c in spec[k])
               for k in ("dataset_sha256","model_sha256")):
        raise HypothesisBlocked("UNPINNED_DATA_OR_MODEL")
    if type(spec["n_trials"]) is not int or spec["n_trials"]<1:
        raise HypothesisBlocked("SEARCH_COUNT_UNKNOWN")
    dev_end=_day(spec["dev_end"])
    hold=_day(spec["holdback_start"])
    hold_end=_day(spec["holdback_end"])
    wf=_day(spec["wf_start"])
    wf_end=_day(spec["wf_end"])
    final=_day(spec["final_holdout_start"])
    asof=_day(spec["asof"])
    universe_asof=_day(spec["universe_asof"])
    if not (dev_end<hold<=hold_end<wf<=wf_end<final<=asof):
        raise HypothesisBlocked("SPLIT_OVERLAP_OR_PREMATURE_HOLDOUT")
    if universe_asof>dev_end:
        raise HypothesisBlocked("FUTURE_CONSTITUENTS_LOOKAHEAD")
    serial=json.dumps(spec,sort_keys=True,separators=(",",":"),allow_nan=False)
    return hashlib.sha256(serial.encode("utf-8")).hexdigest()

def validate_stage(spec: dict, fingerprint: str, stage: str, completed: tuple[str,...]) -> str:
    """Pure stage transition gate; caller must append durable verified records externally."""
    real=register(spec)
    if fingerprint!=real:
        raise HypothesisBlocked("RESEARCH_EVIDENCE_MUTATED")
    stages=("DEV","HOLDBACK","WALK_FORWARD","FINAL_HOLDOUT")
    if stage not in stages:
        raise HypothesisBlocked("UNKNOWN_STAGE")
    if type(completed) is not tuple or any(x not in stages for x in completed):
        raise HypothesisBlocked("INVALID_PREVIOUS_STAGES")
    idx=stages.index(stage)
    if completed!=stages[:idx]:
        raise HypothesisBlocked("OUT_OF_ORDER_OR_REPEATED_HOLDOUT")
    return f"RESEARCH_ONLY:{stage}:VALIDATED_NO_AUTOPROMOTION"

