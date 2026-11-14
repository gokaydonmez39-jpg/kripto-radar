"""Offline #406 Official Witness acceptance. Reads local git objects only.

The caller must independently collect trusted GitHub check and first-main
readback receipts. This module verifies their binding, not their provenance.
It never writes a ref, calls GitHub, or treats a commit date as publication.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import json
import re
import subprocess

GUARD = "nasdaq-xray/canonical_official_source_guard.json"
LEDGER = "nasdaq-xray/official_pit_ledger.json"
CHECK = "xray-477-required-ci"
ACTIONS_APP = 15368
SHA = re.compile(r"[0-9a-f]{40}\Z")
SKIP = ("[skip ci]", "[ci skip]", "[no ci]", "[skip actions]", "[actions skip]")


class Rejected(ValueError):
    pass


def require(ok, code):
    if not ok:
        raise Rejected(code)


def git(root, *args):
    p = subprocess.run(["git", "--no-replace-objects", "-C", str(root), *args],
                       capture_output=True, check=False, timeout=30)
    require(p.returncode == 0, "GIT_READ_FAILED")
    return p.stdout


def doc(root, commit, path):
    value = json.loads(git(root, "show", f"{commit}:{path}"))
    require(isinstance(value, dict), "INVALID_DOCUMENT")
    return value


def utc(stamp):
    require(isinstance(stamp, datetime) and stamp.utcoffset() == timedelta(0),
            "UTC_RECEIPT_REQUIRED")
    return stamp


@dataclass(frozen=True)
class CheckReceipt:
    head: str
    name: str
    app_id: int
    conclusion: str
    finished_at: datetime


@dataclass(frozen=True)
class MainReceipt:
    head: str
    observed_at: datetime
    guard_blob: str
    ledger_blob: str


def check_candidate(root, base, head):
    require(all(isinstance(x, str) and SHA.fullmatch(x) for x in (base, head)),
            "BAD_SHA")
    require(git(root, "rev-list", "--parents", "-n", "1", head).decode().split()
            == [head, base], "STALE_BASE_OR_NOT_SINGLE_PARENT")
    message = git(root, "show", "-s", "--format=%B", head).decode()
    require(not any(marker in message.lower() for marker in SKIP)
            and re.search(r"^skip-checks:\s*true\s*$", message, re.I | re.M) is None,
            "PUSH_CI_SKIPPED")
    changed = git(root, "diff-tree", "--no-renames", "--no-commit-id",
                  "--name-only", "-r", "-z", base, head)
    require(set(changed.split(b"\0")[:-1]) == {GUARD.encode(), LEDGER.encode()},
            "WITNESS_PATHS_MISMATCH")
    for path in (GUARD, LEDGER):
        require(git(root, "ls-tree", head, "--", path).startswith(b"100644 blob "),
                "WITNESS_NOT_REGULAR_FILE")
    g, current, prior = doc(root, head, GUARD), doc(root, head, LEDGER), doc(root, base, LEDGER)
    require(g.get("schema") == "XRAY_OFFICIAL_SOURCE_GUARD_V1"
            and current.get("schema") == "XRAY_OFFICIAL_PIT_LEDGER_V1"
            and prior.get("schema") == current.get("schema"), "SCHEMA_MISMATCH")
    require(all(d.get("execution") == "NONE" and d.get("real_money") == "NO-GO"
                and d.get("alpha_authority") is False for d in (g, current)),
            "SAFETY_FLAGS_MISMATCH")
    require(current.get("append_only_semantics") is True
            and current.get("unknown_never_pass") is True, "LEDGER_FLAGS_MISMATCH")
    old, new = prior.get("snapshots"), current.get("snapshots")
    require(isinstance(old, list) and isinstance(new, list)
            and new[:len(old)] == old and type(current.get("snapshot_count")) is int
            and current["snapshot_count"] == len(new), "LEDGER_NOT_APPEND_ONLY")
    sources = g.get("sources")
    require(isinstance(sources, dict) and {"security_status", "trade_halts"} <= sources.keys()
            and all(isinstance(v, dict) and v.get("status") in {"PASS", "UNKNOWN"}
                    for v in sources.values()), "OFFICIAL_FEEDS_INVALID")
    require(g.get("status") == ("PASS" if all(v["status"] == "PASS"
                                             for v in sources.values()) else "DEGRADED"),
            "OFFICIAL_STATUS_CONFLICT")
    safety = g.get("candidate_safety")
    require(isinstance(safety, dict)
            and safety.get("halt_guard_status") == sources["trade_halts"]["status"]
            and safety.get("security_status_guard_status") == sources["security_status"]["status"],
            "FEED_BINDING_MISMATCH")
    def digest(value):
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                         ensure_ascii=False).encode()).hexdigest()
    witnessed = {(s["source"], s["payload_sha256"]) for s in new
                 if isinstance(s, dict) and isinstance(s.get("source"), str)
                 and isinstance(s.get("payload_sha256"), str)}
    required = {(k, digest(v)) for k, v in {**sources, "candidate_safety": safety}.items()}
    require(required <= witnessed, "LATEST_WITNESS_NOT_LEDGER_BOUND")
    try:
        raw = g["generated_at_utc"]
        generated = utc(datetime.fromisoformat(raw.replace("Z", "+00:00")))
    except (KeyError, TypeError, AttributeError, ValueError):
        raise Rejected("BAD_WITNESS_TIME") from None
    return generated, *(git(root, "rev-parse", f"{head}:{p}").decode().strip()
                        for p in (GUARD, LEDGER))


def check_acceptance(root, base, head, check, readback, cutoff):
    generated, guard_blob, ledger_blob = check_candidate(root, base, head)
    require(check.head == head and check.name == CHECK and check.app_id == ACTIONS_APP
            and check.conclusion == "success", "EXACT_CI_NOT_VERIFIED")
    require(readback.head == head and (readback.guard_blob, readback.ledger_blob)
            == (guard_blob, ledger_blob), "EXACT_MAIN_READBACK_NOT_VERIFIED")
    finished, observed, deadline = map(utc, (check.finished_at, readback.observed_at, cutoff))
    require(generated <= finished <= observed <= deadline, "PIT_VISIBILITY_NOT_PROVED")
    require(observed - generated <= timedelta(minutes=15), "WITNESS_STALE_AT_READBACK")
    return "WITNESS_ACCEPTANCE_PASS"
