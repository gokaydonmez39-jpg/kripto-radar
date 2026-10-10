#!/usr/bin/env python3
"""Pin/verify the historical official Nasdaq directory captured on 2026-10-09.

Independent third-party GitHub archive, MIT code != NASDAQ data license.
NO raw exchange files persisted in repository/artifacts, NO automatic PRIMARY,
issuer alpha/MC/history/G9/ACCOUNT/REAL MONEY authority. Even a fully
matched snapshot is an external replay RESEARCH candidate pending legal and
C4.17 policy review. Only event counts/hashes are retained.
"""
from __future__ import annotations
import argparse
import gzip
import hashlib
import json
import re
import urllib.error
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parent
ASOF="2026-10-09"
SOURCE_REPO="supermodo/us-markets-timemachine"
SOURCE_COMMIT="bdc7e69ea7d21871f2b894096179830d804d4a56"
SOURCE_PATH="data/nasdaq/nasdaqlisted/2026/2026-10-09.txt.gz"
SOURCE_GIT_BLOB="a8f253d1635108a47f195d8002f67a73c41af1e6"
URL=f"https://raw.githubusercontent.com/{SOURCE_REPO}/{SOURCE_COMMIT}/{SOURCE_PATH}"
SCHEMA="XRAY_20261009_NASDAQ_ARCHIVED_DIRECTORY_RESEARCH_PROVENANCE_V1"


def sha_git_blob(blob:bytes)->str:
    return hashlib.sha1(b"blob "+str(len(blob)).encode()+b"\0"+blob).hexdigest()


def parse_archive(compressed:bytes):
    if sha_git_blob(compressed)!=SOURCE_GIT_BLOB:
        raise ValueError("THIRD_PARTY_ARCHIVE_GIT_BLOB_MISMATCH")
    if not compressed.startswith(b"\x1f\x8b"):
        raise ValueError("NASDAQ_ARCHIVE_NOT_GZIP")
    try:
        raw=gzip.decompress(compressed)
        lines=raw.decode("utf-8-sig").splitlines()
    except (OSError,UnicodeDecodeError,EOFError) as exc:
        raise ValueError("NASDAQ_ARCHIVE_GZIP_DECODE_INVALID") from exc
    if len(lines)<500:
        raise ValueError("NASDAQ_ARCHIVE_EMPTY_OR_PARTIAL")
    headers=lines[0].split("|")
    if len(headers)<4 or headers[0]!="Symbol" or headers[1]!="Security Name":
        raise ValueError("NASDAQ_ARCHIVE_WRONG_COLUMNS")
    if lines[-1].startswith("File Creation Time: ") is False:
        raise ValueError("NASDAQ_ARCHIVE_NO_FINAL_FOOTER")
    footer=lines[-1]
    if not re.match(r"^File Creation Time: 10092026\d{2}:\d{2}\|",footer):
        raise ValueError("NASDAQ_ARCHIVE_NOT_EXACT_20261009")
    names={}
    for line in lines[1:-1]:
        cells=line.split("|")
        if len(cells)!=len(headers):
            raise ValueError("NASDAQ_ARCHIVE_ROW_WIDTH_INVALID")
        sym,name=cells[:2]
        if not sym or not name or sym in names:
            raise ValueError("NASDAQ_ARCHIVE_DUPLICATE_OR_EMPTY_SYMBOL")
        names[sym]=name
    return names,footer,hashlib.sha256(raw).hexdigest(),len(raw)


def correlate(names,footer,digest,length):
    full=json.loads((ROOT/"canonical_current_full_state.json").read_text())
    master=json.loads((ROOT/"canonical_current_master_manifest.json").read_text())
    proof=json.loads((ROOT/"master_asof_identity_proof_20261009.json").read_text())
    if (full.get("asof_et")!=ASOF or master.get("asof_et")!=ASOF
         or proof.get("asof_et")!=ASOF
         or full.get("official_footer")!=footer
         or master.get("official_footer")!=footer
         or proof.get("source_directory_footer")!=footer):
        raise ValueError("ARCHIVED_NASDAQ_FOOTER_NOT_CANONICAL_ASOF")
    if (full.get("execution")!="NONE" or master.get("execution")!="NONE"
        or full.get("real_money")!="NO-GO" or master.get("real_money")!="NO-GO"):
        raise ValueError("CANONICAL_POLICY_GATES_CHANGED")
    q=full.get("queue") or []
    master_pass=master.get("pass_symbols") or []
    missing_ids=set(full.get("identity_unknown_symbols") or [])
    if (not isinstance(q,list) or not isinstance(master_pass,list)
        or len(q)!=len(set(q)) or len(master_pass)!=len(set(master_pass))
        or not q or set(q)&missing_ids
        or len(q)+len(missing_ids)!=full.get("raw_identity_total")
        or set(q)!=set(master.get("pass_symbols") or [])):
        raise ValueError("CANONICAL_IDENTITY_PARTITION_UNTRUSTED")
    projected=set(q)|missing_ids
    absent=sorted(projected-set(names))
    unknown_detail=full.get("identity_unknown_detail") or {}
    if set(unknown_detail)!=missing_ids:
        raise ValueError("MISSING_IDENTITY_DETAILS_SOURCE")
    expected_names=dict(full.get("security_names") or {})
    for sym,row in unknown_detail.items():
        n=str((row or {}).get("security_name") or "")
        if not n:raise ValueError("CANONICAL_IDENTITY_NAME_MISSING")
        expected_names[sym]=n
    if set(expected_names)!=projected:
        raise ValueError("CANONICAL_PROJECTED_MEMBERSHIP_NAME_MISMATCH")
    normalize=lambda s:" ".join(s.casefold().split())
    changed=sorted(s for s in projected&set(names)
                   if normalize(expected_names[s])!=normalize(names[s]))
    return {
        "schema":SCHEMA,"asof_et":ASOF,
        "source_repository":SOURCE_REPO,
        "source_commit_sha":SOURCE_COMMIT,
        "source_path":SOURCE_PATH,
        "source_github_git_blob_sha":SOURCE_GIT_BLOB,
        "source_nasdaq_footer":footer,
        "uncompressed_sha256":digest,
        "uncompressed_bytes":length,
        "archive_total_listed_rows":len(names),
        "canonical_projected_symbols":len(projected),
        "canonical_projected_missing_symbols":absent,
        "canonical_projected_name_mismatch_symbols":changed,
        "canonical_projected_symbol_presence_exact":not bool(absent),
        "archived_data_publisher_independently_attested":False,
        "nasdaq_archive_data_usage_rights_attested":False,
        "history_or_market_cap_primary_authority":False,
        "canonical_identity_replay_applied":False,
        "identity_membership_research_status":(
            "ARCHIVED_SAME_ASOF_SOURCE_MATCH_CANDIDATE_NO_GO"
            if not absent and not changed else
            "ARCHIVED_SOURCE_DIFFERS_FROM_CANONICAL_REVIEW_REQUIRED"),
        "execution":"NONE","real_money":"NO-GO",
        "unknown_never_pass":True,
    }


def selftest():
    # Use the same strict parser under a fixture-pinned Git blob identity.
    global SOURCE_GIT_BLOB
    original=SOURCE_GIT_BLOB
    h="Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares"
    lines=[h]+[f"T{i:04d}|Test {i}|Q|N|N|100|N|N" for i in range(510)]
    lines+=["File Creation Time: 1009202621:31|||||||"]
    data="\n".join(lines).encode()+b"\n"
    zipped=gzip.compress(data,mtime=0)
    try:
        SOURCE_GIT_BLOB=sha_git_blob(zipped)
        rows,footer,raw_sha,size=parse_archive(zipped)
        assert len(rows)==510 and footer=="File Creation Time: 1009202621:31|||||||"
        assert raw_sha==hashlib.sha256(data).hexdigest() and size==len(data)
        for corrupt in (
            gzip.compress(data.replace(b"1009202621:31",b"1010202621:31"),mtime=0),
            gzip.compress(data.replace(b"Symbol|Security Name",b"Ticker|Security Name"),mtime=0),
            gzip.compress(data.replace(b"T0001|Test 1",b"T0000|Test 1"),mtime=0),
            b"not a gz",
        ):
            SOURCE_GIT_BLOB=sha_git_blob(corrupt)
            try:parse_archive(corrupt)
            except ValueError:pass
            else:raise AssertionError("BAD_HISTORICAL_NASDAQ_SNAPSHOT_ACCEPTED")
        SOURCE_GIT_BLOB="0"*40
        try:parse_archive(zipped)
        except ValueError:pass
        else:raise AssertionError("HISTORICAL_GIT_SOURCE_BLOB_TAMPERING_ACCEPTED")
    finally:
        SOURCE_GIT_BLOB=original
    print("XRAY_ARCHIVED_NASDAQ_20261009=PASS_GZIP_BLOB_DATE_FOOTER_AND_NEGATIVES_NO_GO")


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--out",type=Path)
    args=p.parse_args()
    if args.selftest:
        selftest();return
    if args.out is None:p.error("--out required")
    request=urllib.request.Request(URL,headers={
        "User-Agent":"NASDAQ-XRAY-20261009-Official-Historical-Snapshot-ReadOnly/1.0"})
    try:
        with urllib.request.urlopen(request,timeout=35) as r:
            if r.status!=200:raise RuntimeError("GITHUB_ARCHIVE_NON200")
            body=r.read(1_000_001)
            if len(body)>1_000_000:raise RuntimeError("GITHUB_ARCHIVE_TOO_LARGE")
    except (urllib.error.HTTPError,urllib.error.URLError,TimeoutError) as err:
        raise SystemExit("GITHUB_HISTORICAL_ARCHIVE_NETWORK_UNAVAILABLE") from err
    names,footer,digest,length=parse_archive(body)
    result=correlate(names,footer,digest,length)
    args.out.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print("XRAY_NASDAQ_ARCHIVE_20261009_STATUS="+result["identity_membership_research_status"])
    print("XRAY_NASDAQ_ARCHIVE_20261009_LISTED="+str(result["archive_total_listed_rows"]))
    print("XRAY_NASDAQ_ARCHIVE_20261009_PROJECTED="+str(result["canonical_projected_symbols"]))
    print("XRAY_NASDAQ_ARCHIVE_20261009_MISSING="+str(len(result["canonical_projected_missing_symbols"])))
    if (result["canonical_projected_missing_symbols"]
        or result["canonical_projected_name_mismatch_symbols"]):
        raise SystemExit(2)


if __name__=="__main__":
    main()
