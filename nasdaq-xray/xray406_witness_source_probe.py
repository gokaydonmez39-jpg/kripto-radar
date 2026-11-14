"""#406 scheduled source rehearsal. No Git writes and no publisher."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import exchange_calendars as xc

NY = ZoneInfo("America/New_York")
REPO = "gokaydonmez39-jpg/kripto-radar"
PREFIX = "nasdaq-xray/"
GUARD = "canonical_official_source_guard.json"
LEDGER = "official_pit_ledger.json"
POINTER = "chatgpt_canonical_state_v2.json"
MODULES = ("official_source_guard.py", "official_pit_ledger.py",
           "resilience_runtime.py", "terminal_official_guard_contract.py")
REQUIRED_FEEDS = {"security_status", "trade_halts", "system_status_ipo",
                  "system_status_selfhelp", "trading_system_adds_deletes"}
SLOTS = {"15 13 * * 1-5": 13, "15 16 * * 1-5": 16}
SHA = re.compile(r"[0-9a-f]{40}\Z")


class Hold(ValueError):
    pass


def need(ok, reason):
    if not ok:
        raise Hold(reason)


def utcnow():
    return datetime.now(timezone.utc)


def utc(value):
    try:
        result = datetime.fromisoformat(value)
        need(result.utcoffset() == timedelta(0), "TIME_NOT_UTC")
        return result
    except (TypeError, ValueError) as exc:
        raise Hold("BAD_UTC_TIMESTAMP") from exc


def scope(env, calendar):
    need((env.get("GITHUB_REPOSITORY"), env.get("GITHUB_EVENT_NAME"),
          env.get("GITHUB_REF"), env.get("GITHUB_RUN_ATTEMPT")) ==
         (REPO, "schedule", "refs/heads/main", "1"), "NOT_NATURAL_MAIN_ATTEMPT_1")
    sha, run, cron = (env.get(k, "") for k in ("GITHUB_SHA", "GITHUB_RUN_ID", "XRAY_PROBE_CRON"))
    need(SHA.fullmatch(sha) and re.fullmatch(r"[1-9][0-9]*", run), "SOURCE_ID_INVALID")
    need(cron in SLOTS, "CRON_ID_INVALID")
    started = utc(env.get("XRAY_SHADOW_RUNNER_STARTED_UTC"))
    asof = started.astimezone(NY).date().isoformat()
    identity = {"repository": REPO, "event": "schedule", "ref": "refs/heads/main",
                "attempt": 1, "run_id": run, "head_sha": sha, "asof_et": asof,
                "cron": cron, "runner_started_at_utc": started.isoformat()}
    if not calendar.is_session(asof):
        return identity, None, "SKIP_XNAS_CLOSED"
    close = calendar.session_close(asof).to_pydatetime().astimezone(timezone.utc)
    slot = close + timedelta(minutes=15)
    cutoff = close + timedelta(minutes=45)
    if slot.astimezone(NY).hour != SLOTS[cron]:
        return identity, None, "SKIP_NONMATCHING_CLOSE"
    need(slot <= started <= cutoff, "RUNNER_OUTSIDE_CLOSE_WINDOW")
    identity.update(xnas_close_utc=close.isoformat(), scheduled_slot_utc=slot.isoformat())
    return identity, cutoff, None


def git(root, *args):
    result = subprocess.run(["git", "--no-replace-objects", "-C", str(root), *args],
                            stdin=subprocess.DEVNULL, capture_output=True, timeout=15, check=False)
    need(result.returncode == 0, "PINNED_GIT_OBJECT_MISSING")
    return result.stdout


def read_pinned(root, commit, path):
    path = PREFIX + path
    tree = git(root, "ls-tree", "-z", commit, "--", path)
    fields = tree.removesuffix(b"\0").split(b"\t")
    need(len(fields) == 2 and fields[1] == path.encode(), "PINNED_PATH_MISSING")
    kind = fields[0].split()
    need(len(kind) == 3 and kind[:2] == [b"100644", b"blob"], "PINNED_PATH_NOT_REGULAR")
    blob = kind[2].decode()
    need(SHA.fullmatch(blob), "PINNED_BLOB_INVALID")
    data = git(root, "cat-file", "blob", blob)
    need(blob == blob_id(data), "PINNED_BLOB_MISMATCH")
    return data


def blob_id(data):
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def digest(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode()).hexdigest()


def doc(data):
    try:
        value = json.loads(data)
    except (ValueError, UnicodeError):
        raise Hold("PAYLOAD_JSON_INVALID") from None
    need(isinstance(value, dict), "PAYLOAD_SHAPE_INVALID")
    return value


def deadline(generated, cutoff):
    return min(generated + timedelta(minutes=15), cutoff)


def paired(identity, cutoff, began, finished, original, guard_bytes, ledger_bytes):
    prior, guard, ledger = map(doc, (original, guard_bytes, ledger_bytes))
    need(guard.get("schema") == "XRAY_OFFICIAL_SOURCE_GUARD_V1" and
         prior.get("schema") == ledger.get("schema") == "XRAY_OFFICIAL_PIT_LEDGER_V1",
         "SCHEMA_MISMATCH")
    for data in (prior, guard, ledger):
        need(data.get("execution") == "NONE" and data.get("real_money") == "NO-GO" and
             data.get("alpha_authority") is False, "AUTHORITY_FLAGS_MISMATCH")
    need(all(d.get("append_only_semantics") is True and d.get("unknown_never_pass") is True
             for d in (prior, ledger)), "LEDGER_NOT_FAIL_CLOSED")
    old, new = prior.get("snapshots"), ledger.get("snapshots")
    need(isinstance(old, list) and isinstance(new, list) and new[:len(old)] == old and
         type(ledger.get("snapshot_count")) is int and ledger["snapshot_count"] == len(new) and
         (("snapshot_count" not in prior and not old) or prior.get("snapshot_count") == len(old)),
         "LEDGER_NOT_APPEND_ONLY")
    generated, ingested = utc(guard.get("generated_at_utc")), utc(ledger.get("last_ingest_at_utc"))
    limit = deadline(generated, cutoff)
    need(began <= generated <= ingested <= finished <= limit, "SOURCE_TIME_OUTSIDE_WINDOW")
    need(generated.astimezone(NY).date().isoformat() == identity["asof_et"], "GENERATED_ASOF_MISMATCH")
    sources = guard.get("sources")
    need(isinstance(sources, dict) and set(sources) == REQUIRED_FEEDS and
         all(isinstance(v, dict) and v.get("status") in ("UNKNOWN", "PASS")
             for v in sources.values()), "FEED_SET_INVALID")
    safety = guard.get("candidate_safety")
    need(isinstance(safety, dict) and
         safety.get("security_status_guard_status") == sources["security_status"]["status"] and
         safety.get("halt_guard_status") == sources["trade_halts"]["status"],
         "SAFETY_FEED_BINDING")
    status = "PASS" if all(v["status"] == "PASS" for v in sources.values()) else "DEGRADED"
    need(guard.get("status") == ledger.get("status") == status, "SOURCE_STATUS_MISMATCH")
    observed = set()
    for index, snap in enumerate(new):
        need(isinstance(snap, dict) and isinstance(snap.get("source"), str) and
             isinstance(snap.get("payload"), dict) and
             digest(snap["payload"]) == snap.get("payload_sha256"), "SNAPSHOT_PAYLOAD_DIGEST_INVALID")
        key = (snap["source"], snap["payload_sha256"])
        if index >= len(old):
            need(key not in observed, "LEDGER_NEW_SNAPSHOT_DUPLICATE")
            need(utc(snap.get("guard_generated_at_utc")) == generated and
                 generated <= utc(snap.get("observed_at_utc")) <= ingested, "NEW_SNAPSHOT_TIME_MISMATCH")
        observed.add(key)
    need({(key, digest(x)) for key, x in {**sources, "candidate_safety": safety}.items()}
         <= observed, "LEDGER_DIGEST_BINDING_MISSING")
    if sources["security_status"]["status"] == "PASS":
        today = sources["security_status"]
        need(today.get("query_end") == identity["asof_et"], "PROVIDER_ASOF_MISMATCH")
        try:
            need(date.fromisoformat(today["query_start"]) <= date.fromisoformat(today["query_end"]),
                 "PROVIDER_QUERY_INVERTED")
        except (KeyError, TypeError, ValueError) as exc:
            raise Hold("PROVIDER_QUERY_RANGE_INVALID") from exc
    required = ("security_status", "trade_halts")
    state = ("SOURCE_PAIR_OBSERVED_ONLY" if all(sources[k]["status"] == "PASS" for k in required)
             else "HOLD_REQUIRED_OFFICIAL_FEED")
    return dict(identity, state=state, generated_at_utc=generated.isoformat(),
                source_finished_at_utc=finished.isoformat(), deadline_utc=limit.isoformat(),
                remaining_for_ci_and_readback_seconds=int((limit-finished).total_seconds()),
                guard_blob=blob_id(guard_bytes), ledger_blob=blob_id(ledger_bytes),
                prior_ledger_blob=blob_id(original), feed_states={k: v["status"] for k,v in sources.items()},
                guard_status=status, source_ready=state == "SOURCE_PAIR_OBSERVED_ONLY")


def run(root, env, *, calendar=None, clock=utcnow):
    if calendar is None:
        calendar = xc.get_calendar("XNAS")
    markers = {"schema": "XRAY406_SOURCE_PROBE_V1", "published": False,
               "first_visibility_verified": False, "market_clearance": False,
               "may_promote": False, "canonical_writes": 0}
    identity = {}
    try:
        identity, cutoff, skip = scope(env, calendar)
        if skip:
            return dict(markers, **identity, state=skip)
        commit = identity["head_sha"]
        need(git(root, "rev-parse", "HEAD").decode().strip() == commit, "CHECKOUT_SHA_MISMATCH")
        with tempfile.TemporaryDirectory(prefix="xray406-source-") as tmp:
            work = Path(tmp)
            for filename in (*MODULES, LEDGER, POINTER):
                (work / filename).write_bytes(read_pinned(root, commit, filename))
            prior = (work/LEDGER).read_bytes()
            history = doc(prior)
            need(history.get("schema") == "XRAY_OFFICIAL_PIT_LEDGER_V1" and
                 isinstance(history.get("snapshots"), list) and
                 history.get("append_only_semantics") is True and
                 history.get("unknown_never_pass") is True and history.get("execution") == "NONE" and
                 history.get("real_money") == "NO-GO" and history.get("alpha_authority") is False,
                 "PRIOR_LEDGER_INVALID")
            raw = doc((work/POINTER).read_bytes()).get("state_json")
            pointer = doc(raw) if isinstance(raw, str) else raw
            try:
                pointer_date = date.fromisoformat(pointer["asof_et"])
                need(pointer_date <= date.fromisoformat(identity["asof_et"]), "POINTER_FROM_FUTURE")
            except (TypeError, KeyError, ValueError) as exc:
                raise Hold("POINTER_ASOF_INVALID") from exc
            began = clock()
            need(utc(identity["runner_started_at_utc"]) <= began <= cutoff,
                 "SOURCE_START_OUTSIDE_WINDOW")
            allow = {"PATH", "LANG", "LC_ALL", "LC_CTYPE", "TZ", "SSL_CERT_FILE", "SSL_CERT_DIR"}
            child_env = {key: value for key, value in env.items() if key in allow}
            for module in ("official_source_guard.py", "official_pit_ledger.py"):
                remaining = (min(cutoff, began + timedelta(minutes=15)) - clock()).total_seconds()
                need(remaining > 0, "SOURCE_DEADLINE_EXPIRED")
                run_result = subprocess.run([sys.executable, "-I", "-B", "-c", _CHILD,
                    module], cwd=work, env=child_env, stdin=subprocess.DEVNULL,
                    capture_output=True, timeout=min(420, remaining), check=False)
                need(run_result.returncode == 0, "OFFICIAL_SOURCE_PROCESS_FAILED")
            g, l = (work/GUARD).read_bytes(), (work/LEDGER).read_bytes()
            receipt = paired(identity, cutoff, began, clock(), prior, g, l)
        return dict(markers, **receipt)
    except Hold as exc:
        return dict(markers, **identity, state="HOLD", reason=str(exc))
    except subprocess.TimeoutExpired:
        return dict(markers, **identity, state="HOLD", reason="SOURCE_OR_READ_TIMEOUT")
    except (OSError, UnicodeError, ValueError, OverflowError):
        return dict(markers, **identity, state="HOLD", reason="EVIDENCE_NOT_READABLE")


# Extra transport checks are shadow-only. Do not change the existing producer.
_CHILD = """
import runpy, sys
from xml.etree import ElementTree
sys.path.insert(0, ".")
module = sys.argv[1]
sys.argv = [module]
if module == "official_source_guard.py":
    import resilience_runtime
    fetch = resilience_runtime.fetch_text
    def observed_transport(provider, url, *args, **kwargs):
        data = fetch(provider, url, *args, **kwargs)
        if provider in {"NASDAQ_TRADE_HALTS", "NASDAQ_SYSTEM_STATUS_IPO",
                        "NASDAQ_SYSTEM_STATUS_SELFHELP"}:
            root = ElementTree.fromstring(data)
            if root.tag != "rss" or len(root.findall("./channel")) != 1:
                raise ValueError("UNVERIFIED_NASDAQ_RSS_CONTAINER")
        return data
    resilience_runtime.fetch_text = observed_transport
runpy.run_path(module, run_name="__main__")
"""


def main():
    result = run(Path.cwd(), os.environ)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["state"].startswith(("SOURCE_PAIR_", "SKIP_")) else 1


if __name__ == "__main__":
    sys.exit(main())
