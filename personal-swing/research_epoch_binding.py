"""Same-run fence for existing Personal 477 research children (no I/O writes)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path
import re


REPO = "gokaydonmez39-jpg/kripto-radar"
EOD_PATH = ".github/workflows/xray-personal-477-eod.yml"
EOD_WEB = "https://github.com/" + REPO + "/actions/runs/"
MAX_EVENT_BYTES = 1024 * 1024


class EpochBindingError(ValueError):
    """Fixed diagnostic only, never interpolates a webhook or Sheet value."""


@dataclass(frozen=True)
class Parent:
    run_id: int
    head_sha: str


def _require(ok, reason):
    if not ok:
        raise EpochBindingError(reason)


def _unique(pairs):
    out = {}
    for k, v in pairs:
        _require(k not in out, "DUPLICATE_PARENT_EVENT_FIELD")
        out[k] = v
    return out


def _nonfinite(_literal):
    raise EpochBindingError("INVALID_PARENT_EVENT_JSON")


def _id(x):
    return type(x) is int and 0 < x <= 2**53 - 1


def _same_repo(obj):
    return type(obj) is dict and obj.get("full_name") == REPO


def _sha(value):
    return type(value) is str and re.fullmatch(r"[a-f0-9]{40}", value) is not None


def scheduled_parent(environ):
    """Bind the official Actions event payload, not an assumed sibling run."""
    _require(environ.get("GITHUB_EVENT_NAME") == "workflow_run"
             and environ.get("GITHUB_REPOSITORY") == REPO,
             "NOT_PERSONAL_RESEARCH_WORKFLOW_EVENT")
    name = environ.get("GITHUB_EVENT_PATH")
    _require(type(name) is str and bool(name), "PARENT_EVENT_UNAVAILABLE")
    try:
        with Path(name).open("rb") as event_file:
            raw = event_file.read(MAX_EVENT_BYTES + 1)
        _require(0 < len(raw) <= MAX_EVENT_BYTES, "PARENT_EVENT_SIZE")
        event = json.loads(raw, object_pairs_hook=_unique, parse_constant=_nonfinite)
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise EpochBindingError("PARENT_EVENT_UNREADABLE") from None
    _require(type(event) is dict and event.get("action") == "completed"
             and _same_repo(event.get("repository")), "PARENT_EVENT_IDENTITY")
    run = event.get("workflow_run")
    _require(type(run) is dict and run.get("path") == EOD_PATH
             and run.get("head_branch") == "main"
             and _same_repo(run.get("head_repository"))
             and run.get("event") == "schedule"
             and type(run.get("run_attempt")) is int and run["run_attempt"] == 1
             and run.get("status") == "completed" and run.get("conclusion") == "success"
             and _id(run.get("id")) and _sha(run.get("head_sha")),
             "PARENT_NOT_EXACT_NATURAL_EOD")
    return Parent(run["id"], run["head_sha"])


def verify_sheet_parent(parent, scan_url, score_url):
    """Both already-read canonical receipts must point to the triggered EOD."""
    _require(type(parent) is Parent and _id(parent.run_id) and _sha(parent.head_sha),
             "INVALID_PARENT_BINDING")
    base = re.escape(EOD_WEB + str(parent.run_id))
    _require(type(scan_url) is str and type(score_url) is str and scan_url == score_url
             and re.fullmatch(base + r"(?:/jobs/[1-9][0-9]*)?", scan_url) is not None,
             "PARENT_SHEET_RECEIPTS_MISMATCH")


def redacted_parent(parent, asof):
    """Only three aggregate/public fields, emitted after private verification."""
    _require(type(parent) is Parent and _id(parent.run_id) and _sha(parent.head_sha),
             "INVALID_PARENT_BINDING")
    try:
        valid = type(asof) is str and date.fromisoformat(asof).isoformat() == asof
    except ValueError:
        valid = False
    _require(valid, "INVALID_PARENT_ASOF")
    return {"asof_et": asof, "eod_run_id": parent.run_id, "eod_head_sha": parent.head_sha}
