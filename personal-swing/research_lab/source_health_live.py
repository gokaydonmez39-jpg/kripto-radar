"""Unattended, READ-ONLY four-source provenance observer for Personal 477.

This runs in the EXISTING Research Source Lab schedule. It never drives the
canonical AL/STOP/B paths, never writes to Sheets, and never claims delivery.
Only aggregate statuses appear in public Actions logs. Missing or contradictory
proof is UNKNOWN/HOLD, not a fabricated healthy source.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE.parent))
import source_health as contract

REPO = "gokaydonmez39-jpg/kripto-radar"
ROOT = "https://github.com/" + REPO + "/actions/runs/"
ID = re.compile(r"^[1-9][0-9]*$")
RUN_NAMES = {
    "KRONOS_V2": ("xray-personal-kronos-shadow.yml", "kronos-v2-full-477-research"),
    "COVE": ("xray-personal-cove-shadow.yml", "private-eod-research"),
}
SCAN_HEADER = ["ASOF ET", "ÜRETİM KANALI", "İSTENEN", "İŞLENEN", "GEÇERLİ",
               "EKSİK", "FINAL READY", "YENİ KAYIT", "RUN KANITI", "DURUM / VERİ SINIRI"]


class NoProof(ValueError):
    """Expected fail-closed lack of evidence, never includes source payloads."""


def require(ok):
    if not ok:
        raise NoProof("EVIDENCE_NOT_VERIFIED")


def safe_id(value):
    return type(value) is int and 0 < value <= 2**53 - 1


def aggregate(github, sheets, current_asof):
    """Build four independent structural receipts; code never sends notifications."""
    scan = sheets.read("TARAMA_KAYITLARI", "J")
    scores = sheets.read("SWING_SKOR_GUNLUK", "AI")
    require(scan and scan[0] == SCAN_HEADER and scores and scores[0][:5] ==
            ["KAYIT_KIMLIGI", "ASOF_ET", "EPIZOT_KIMLIGI", "SEMBOL", "KAYIT_TIPI"])
    recent = [r for r in scan[1:] if r and r[0]]
    require(len(recent) > 0)
    tail = recent[-1]
    require(tail[0] == current_asof and len(tail) >= 10)
    require([str(tail[i]) for i in (2, 3, 4, 5, 6)] ==
            ["477", "477", "477", "0", "TRUE"])
    proof_url = str(tail[8])
    require(proof_url.startswith(ROOT) and ID.fullmatch(proof_url[len(ROOT):]) is not None)
    eid = int(proof_url[len(ROOT):])
    summary = [r for r in scores[1:] if len(r) >= 29 and r[0] == current_asof + "|SUMMARY"
               and r[1] == current_asof and r[4] == "SUMMARY"]
    require(len(summary) == 1 and summary[0][26] == proof_url and
            summary[0][27] in ("READY_FOR_CHATGPT_DAILY_DIGEST", "ALERT_REQUESTED_NOT_DEVICE_ACK"))

    erun = github.json("/actions/runs/" + str(eid))
    require(erun.get("id") == eid and erun.get("path") == contract.EOD and
            erun.get("event") == "schedule" and erun.get("head_branch") == "main" and
            erun.get("run_attempt") == 1 and erun.get("status") == "completed" and
            erun.get("conclusion") == "success" and
            erun.get("head_repository", {}).get("full_name") == REPO)
    head = erun.get("head_sha")
    require(contract._valid_sha(head))
    jobs = github.json("/actions/runs/" + str(eid) + "/jobs?per_page=100")
    job_map = {j.get("name"): j for j in jobs.get("jobs", []) if j.get("name")}
    required = ("daily-private-scan", "private-episode-followups", "guardian-acceptance",
                "daily-private-score-acceptance")
    require(len(job_map) == len(jobs.get("jobs", [])) and
            all(job_map.get(n, {}).get("conclusion") == "success" for n in required))

    def norm_run(run):
        return dict(id=run["id"], path=run["path"], repository=REPO,
                    branch=run["head_branch"], head_sha=run["head_sha"],
                    attempt=run["run_attempt"], event=run["event"],
                    status=run["status"], conclusion=run["conclusion"])

    def receipt(source, run, result, metrics):
        return dict(source=source, asof=current_asof, eod_run_id=eid,
                    eod_head_sha=head, run=norm_run(run), result=result,
                    metrics=metrics)

    core = receipt("CORE", erun, "CORE_EOD_READBACK_VERIFIED", {
        "requested": 477, "processed": 477, "valid": 477, "missing": 0,
        "history_sessions": 52, "feed": "ALPACA_IEX_RAW_1DAY", "calendar": "XNAS",
        "final_ready": True, "guardian_verified": True, "score_verified": True})
    # `history_sessions` is the enforced EOD contract, NOT an independently
    # observed 52-bar data sample. CORE is a structural corroboration only.
    proofs = [core]
    incomplete = {}

    def clean_log(job_id):
        raw = github.text("/actions/jobs/" + str(job_id) + "/logs")
        # GitHub logs can include echoed shell source; only actual emitted lines.
        return "\n".join(x for x in raw.splitlines()
                         if "\x1b[" not in x and "##[group]" not in x and
                         "##[endgroup]" not in x)

    # Independent official witness from the *same* verified EOD producer job.
    try:
        official_log = clean_log(job_map["daily-private-scan"]["id"])
        require('"official_shadow_receipt": "RESEARCH_LEDGER_READBACK_PASS_NO_MARKET_CLEARANCE"' in official_log
                and '"market_clearance_proven": false' in official_log and
                '"corporate_actions_unknown": 477' in official_log)
        proofs.append(receipt("OFFICIAL_477", erun,
                             "RESEARCH_LEDGER_READBACK_PASS_NO_MARKET_CLEARANCE",
                             {"rows": 477, "pit_verified": False, "market_clearance": False}))
    except (NoProof, KeyError, ValueError, OSError):
        incomplete["OFFICIAL_477"] = "OFFICIAL_LOG_NOT_VERIFIED"

    # The child event is not proof of parentage. Parse each child's own
    # redacted parent marker, generated *after* authenticated scan/score readback.
    for source, (workflow, name) in RUN_NAMES.items():
        try:
            results = github.json("/actions/workflows/" + workflow +
                                  "/runs?event=workflow_run&per_page=60")
            candidates = []
            for run in results.get("workflow_runs", []):
                if (run.get("path") != contract.WORKFLOWS[source] or
                    run.get("event") != "workflow_run" or
                    run.get("head_branch") != "main" or run.get("head_sha") != head or
                    run.get("status") != "completed" or run.get("conclusion") != "success" or
                    run.get("head_repository", {}).get("full_name") != REPO or
                    run.get("run_attempt") != 1 or not safe_id(run.get("id"))):
                    continue
                rjobs = github.json("/actions/runs/" + str(run["id"]) + "/jobs?per_page=100")
                found = [j for j in rjobs.get("jobs", []) if j.get("name") == name and
                         j.get("conclusion") == "success"]
                if len(found) != 1:
                    continue
                log = clean_log(found[0]["id"])
                if source == "COVE":
                    markers = re.findall(r"COVE_SOURCE_PARENT_V1=(\{[^\r\n]*\})", log)
                    require(len(markers) <= 1)
                    if not markers:
                        continue
                    marker = json.loads(markers[0])
                    if (marker.get("asof_et") != current_asof or
                        marker.get("eod_run_id") != eid or
                        marker.get("eod_head_sha") != head or
                        "COVE_SHADOW_POST_EOD=READONLY_RESEARCH_PASS_NO_PUBLIC_METRICS" not in log):
                        continue
                    candidates.append(receipt(source, run,
                        "READONLY_RESEARCH_PASS_NO_PUBLIC_METRICS", {}))
                else:
                    # Kronos writes an aggregate JSON log *after* private
                    # forecast readback. GitHub may mask curly braces; parse
                    # bounded numeric/public fields from the same log line.
                    lines = [l for l in log.splitlines() if
                             '"eod_run_id": ' in l and
                             '"eod_head_sha": ' in l and
                             '"asof_et": ' in l and
                             '"status": "KRONOS2_PRIVATE_READBACK_' in l]
                    require(len(lines) <= 1)
                    if not lines:
                        continue
                    line = lines[0]
                    def field(k):
                        match = re.search(r'"' + re.escape(k) + r'": (\d+)(?:[,\s]|$)', line)
                        require(match is not None)
                        return int(match.group(1))
                    if (f'"asof_et": "{current_asof}"' not in line or
                        f'"eod_run_id": {eid}' not in line or
                        f'"eod_head_sha": "{head}"' not in line or
                        field("scope") != 477 or field("rows_written") != 1431):
                        continue
                    full, close, hold = (field("full_geometry"), field("close_only"), field("qc_hold"))
                    require(full + close + hold == 477 and hold == 0)
                    # Private Sheet readback independently corroborates the
                    # public aggregate log. Never expose any symbol or price.
                    partition = sheets.read("KRONOS2_" + current_asof[:4] +
                                            "_" + current_asof[5:7], "T")
                    require(partition and partition[0][:5] ==
                            ["KAYIT_KIMLIGI", "ASOF_ET", "SEMBOL",
                             "UFUK_SEANS", "SON_IEX_KAPANIS_USD"])
                    current_rows = [r for r in partition[1:]
                                    if len(r) >= 20 and r[1] == current_asof]
                    require(len(current_rows) == 1431)
                    symbols = {}
                    identities = set()
                    for r in current_rows:
                        require(r[0] and r[0] not in identities and
                                r[2] and r[3] in ("1", "5", "12") and
                                r[13] and r[14] and r[15] and r[19] and
                                r[17] in ("RESEARCH_ONLY", "RESEARCH_CLOSE_ONLY"))
                        identities.add(r[0])
                        horizon_map = symbols.setdefault(r[2], {})
                        require(r[3] not in horizon_map)
                        horizon_map[r[3]] = r[17]
                    require(len(symbols) == 477 and
                            all(set(v) == {"1", "5", "12"} and
                                len(set(v.values())) == 1
                                for v in symbols.values()))
                    sheet_full = sum(1 for v in symbols.values()
                                     if v["1"] == "RESEARCH_ONLY")
                    require(sheet_full == full and 477 - sheet_full == close)
                    quality = "CLOSE_ONLY" if close else "FULL_GEOMETRY"
                    require('"status": "KRONOS2_PRIVATE_READBACK_' + quality + '"' in line)
                    candidates.append(receipt(source, run,
                        "KRONOS2_PRIVATE_READBACK_" + quality,
                        {"symbols": 477, "rows": 1431, "horizons": [1, 5, 12],
                         "full_geometry": full, "close_only": close, "qc_hold": hold}))
            require(len(candidates) <= 1)
            if candidates:
                proofs.append(candidates[0])
            else:
                incomplete[source] = "NO_EXACT_PARENTED_CHILD_RECEIPT"
        except Exception:
            incomplete[source] = "CHILD_RECEIPT_UNVERIFIED"

    health = contract.observe(asof=current_asof, eod_run_id=eid, eod_head_sha=head,
                              receipts=proofs)
    # Missing child is UNKNOWN, never a false healthy result. No private cells
    # or raw provider data leave this function.
    return health, incomplete


class GitHubReader:
    """Bounded, authenticated, read-only GitHub REST API client."""
    def __init__(self, token):
        require(bool(token))
        self.token = token

    def _get(self, path):
        require(path.startswith("/actions/") and ".." not in path and len(path) < 250)
        u = "https://api.github.com/repos/" + REPO + path
        req = Request(u, headers={"Authorization": "Bearer " + self.token,
                                  "Accept": "application/vnd.github+json",
                                  "X-GitHub-Api-Version": "2022-11-28"})
        with urlopen(req, timeout=20) as response:
            body = response.read(2_000_001)
        require(len(body) <= 2_000_000)
        return body

    def json(self, path):
        value = json.loads(self._get(path))
        require(type(value) is dict)
        return value

    def text(self, path):
        return self._get(path).decode("utf-8", errors="replace")


def main():
    try:
        import engine
        import private_sheet_writer as writer
        need = ("GITHUB_TOKEN", "XRAY_PRIVATE_SHEET_SERVICE_ACCOUNT_JSON",
                "XRAY_PRIVATE_SPREADSHEET_ID")
        require(all(os.environ.get(name) for name in need))
        class ReadOnlySheet(writer.SheetApi):
            def request(self, path, *, method="GET", body=None):
                require(method == "GET" and body is None)
                return super().request(path, method="GET")
            def apply(self, *args, **kwargs):
                raise NoProof("WRITE_DISABLED")

        api = ReadOnlySheet(os.environ["XRAY_PRIVATE_SHEET_SERVICE_ACCOUNT_JSON"])
        api.check_metadata()
        current = engine.trading_asof().isoformat()
        health, gaps = aggregate(GitHubReader(os.environ["GITHUB_TOKEN"]), api, current)
        states = {k: v["state"] for k, v in health["sources"].items()}
        # ONLY aggregate states and previously public source EOD run id.
        print("XRAY_SOURCE_HEALTH_AUTO_V1=" + json.dumps({
            "asof": health["asof"], "eod_run_id": health["eod_run_id"],
            "sources": states, "gaps": gaps,
            "may_notify": False, "may_trade": False,
            "decision_influence": "NO_GO"}, sort_keys=True))
        return 0 if all(s.startswith("MATCHED_") for s in states.values()) else 3
    except Exception:
        # Never leak authenticated HTTP response, sheet IDs, raw private rows,
        # account credentials, symbols, upstream data or exception details.
        print("XRAY_SOURCE_HEALTH_AUTO_V1=HOLD_UNVERIFIED_NO_DATA_PUBLISHED")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())