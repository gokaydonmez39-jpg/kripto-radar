#!/usr/bin/env python3
"""Source-epoch-bound GitHub CAS publisher for personal research labels ONLY.

Does not fetch market data, authorize AL, issue R92, or place orders.
An unrelated main HEAD advancement is safe; SOURCE blob advancement is not.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.request

SOURCES = {
    "nasdaq-xray/orchestrator_state.json": "orchestrator_blob_sha",
    "nasdaq-xray/canonical_current_master_manifest.json": "master_blob_sha",
    "nasdaq-xray/canonical_current_price_dv30.json": "canonical_price_blob_sha",
}
TARGET = "/contents/nasdaq-xray/personal_swing_radar_current.json"
SCHEMA = "XRAY_PERSONAL_SWING_RADAR_DAILY_SNAPSHOT_V1"


def require(ok, reason):
    if not ok:
        raise ValueError("XRAY_PERSONAL_EOD_PUBLISH_" + reason)


def validate(raw):
    doc = json.loads(raw)
    require(type(doc) is dict and doc.get("schema") == SCHEMA, "SCHEMA")
    require(doc.get("completed_session_latest") is True, "COMPLETED_SESSION")
    require(doc.get("registered_R92_signal_count") == 0, "RESEARCH_R92_NONZERO")
    require(doc.get("no_vendor_ohlcv_or_price_levels_persisted") is True,
            "VENDOR_DATA_PRESENT")
    safety = doc.get("safety") or {}
    require(safety.get("execution") == "NONE" and
            safety.get("real_money") == "NO-GO", "SAFETY")
    pins = doc.get("asof_proof")
    require(type(pins) is dict, "SOURCE_BINDINGS_ABSENT")
    for key in SOURCES.values():
        require(type(pins.get(key)) is str and
                re.fullmatch(r"[0-9a-f]{40}", pins[key]) is not None,
                "INVALID_GIT_SHA_" + key)
    require(type(doc.get("asof_et")) is str and
            re.fullmatch(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}",
                         doc["asof_et"]) is not None, "ASOF")
    return doc


def decode_contents(row):
    require(type(row) is dict and type(row.get("sha")) is str,
            "DESTINATION_READ_INVALID")
    content = row.get("content")
    require(type(content) is str, "DESTINATION_BYTES_MISSING")
    return base64.b64decode(content, validate=True)


def source_matches(call, doc):
    for path, key in SOURCES.items():
        result = call("/contents/" + path + "?ref=main")
        require(type(result) is dict and
                result.get("sha") == doc["asof_proof"][key],
                "SOURCE_BLOB_DRIFT_NO_WRITE_" + key)


def publish(raw, call):
    doc = validate(raw)
    # Branch HEAD is diagnostic only. DATA SOURCE identity is exact blob SHA.
    head = call("/branches/main")
    require(type(head) is dict and
            re.fullmatch(r"[0-9a-f]{40}",
                         str((head.get("commit") or {}).get("sha", ""))),
            "BRANCH_UNREADABLE")
    source_matches(call, doc)
    prev = call(TARGET + "?ref=main", missing_ok=True)
    if prev is not None:
        old_bytes = decode_contents(prev)
        if old_bytes == raw:
            source_matches(call, doc)
            return "PASS_ALREADY_EXACT"
        old = json.loads(old_bytes)
        require(type(old) is dict and
                old.get("schema") == SCHEMA and
                type(old.get("asof_et")) is str and
                old["asof_et"] <= doc["asof_et"],
                "OLDER_SNAPSHOT_OVERWRITE_BLOCKED")
    request = {
        "message": "chore(xray): persist verified personal EOD research status [skip ci]",
        "content": base64.b64encode(raw).decode("ascii"),
        "branch": "main",
    }
    if prev is not None:
        request["sha"] = prev["sha"]  # Contents API compare-and-swap.
    call(TARGET, "PUT", request)
    verify = call(TARGET + "?ref=main")
    require(decode_contents(verify) == raw, "POST_WRITE_BYTES_MISMATCH")
    # A new source commit during the PUT can make the resulting snapshot stale.
    # Fail closed, never report a valid publication in this race.
    source_matches(call, doc)
    return "PASS_SAME_BYTES_SAME_ASOF"


def rest_client():
    token = os.environ["GH_TOKEN"]
    repo = os.environ["GITHUB_REPOSITORY"]
    url = "https://api.github.com/repos/" + repo
    headers = {
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "xray-personal-eod-verified-cas",
    }

    def call(path, method="GET", body=None, missing_ok=False):
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(url + path, data=data,
                                         method=method, headers=headers)
        if data is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=18) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as error:
            if error.code == 404 and missing_ok:
                return None
            raise
    return call


def selftest():
    import copy
    pins = {name: chr(97 + i) * 40 for i, name in
            enumerate(SOURCES.values())}
    doc = {
        "schema": SCHEMA, "asof_et": "2026-10-14",
        "completed_session_latest": True,
        "registered_R92_signal_count": 0,
        "no_vendor_ohlcv_or_price_levels_persisted": True,
        "safety": {"execution": "NONE", "real_money": "NO-GO"},
        "asof_proof": pins,
    }
    raw = (json.dumps(doc, sort_keys=True) + "\n").encode("utf-8")

    class Fake:
        def __init__(self):
            self.head = "f" * 40  # unrelated branch advancement.
            self.sources = dict(pins)
            self.data = (json.dumps(dict(doc, asof_et="2026-10-13"),
                                    sort_keys=True) + "\n").encode()
            self.writes = 0
            self.corrupt = False
            self.drift_after = False
        def __call__(self, path, method="GET", body=None, missing_ok=False):
            if path == "/branches/main":
                return {"commit": {"sha": self.head}}
            if path.startswith("/contents/nasdaq-xray/") and path != TARGET and method == "GET":
                for source_path, key in SOURCES.items():
                    if path == "/contents/" + source_path + "?ref=main":
                        val = self.sources[key]
                        if self.drift_after and self.writes:
                            val = "0" * 40
                        return {"sha": val}
            if path == TARGET + "?ref=main":
                if self.data is None:
                    return None
                return {"sha": "e" * 40,
                        "content": base64.b64encode(self.data + (b"!" if
                                    self.corrupt and self.writes else b"")).decode()}
            if path == TARGET and method == "PUT":
                require(body.get("sha") == ("e" * 40 if self.data is not None else None),
                        "MOCK_CAS_MISSING")
                self.writes += 1
                self.data = base64.b64decode(body["content"], validate=True)
                return {"commit": {"sha": "d" * 40}}
            raise AssertionError("MOCK_ENDPOINT_UNEXPECTED_" + path)

    good = Fake()
    assert publish(raw, good) == "PASS_SAME_BYTES_SAME_ASOF"
    assert good.writes == 1 and good.data == raw
    assert publish(raw, good) == "PASS_ALREADY_EXACT" and good.writes == 1

    def negative(setup, expected, write_count=0):
        local_doc = copy.deepcopy(doc)
        fake = Fake()
        setup(local_doc, fake)
        source = (json.dumps(local_doc, sort_keys=True) + "\n").encode()
        try:
            publish(source, fake)
        except ValueError as exc:
            assert expected in str(exc), (expected, str(exc))
        else:
            raise AssertionError("UNSAFE_PUBLISH_ACCEPTED_" + expected)
        assert fake.writes == write_count, (expected, fake.writes)

    negative(lambda d, f: f.sources.update(orchestrator_blob_sha="0"*40),
             "SOURCE_BLOB_DRIFT")
    negative(lambda d, f: d.update(registered_R92_signal_count=1),
             "RESEARCH_R92_NONZERO")
    negative(lambda d, f: d["safety"].update(execution="LIVE"),
             "SAFETY")
    negative(lambda d, f: d.update(asof_et="2026-10-12"),
             "OLDER_SNAPSHOT_OVERWRITE_BLOCKED")
    negative(lambda d, f: setattr(f, "corrupt", True),
             "POST_WRITE_BYTES_MISMATCH", 1)
    negative(lambda d, f: setattr(f, "drift_after", True),
             "SOURCE_BLOB_DRIFT", 1)
    print("XRAY_PERSONAL_EOD_CAS_SELFTEST=PASS_6_NEGATIVES_UNRELATED_HEAD_SAFE_SOURCE_SHA_STRICT")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--snapshot", type=Path)
    args = parser.parse_args()
    if args.selftest:
        selftest()
        return
    require(args.snapshot is not None and args.snapshot.is_file(),
            "SNAPSHOT_PATH_MISSING")
    status = publish(args.snapshot.read_bytes(), rest_client())
    print("XRAY_PERSONAL_EOD_GITHUB_READBACK=" + status)


if __name__ == "__main__":
    main()
