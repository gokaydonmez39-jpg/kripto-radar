#!/usr/bin/env python3
"""Exact four-artifact disjoint reconciliation of full 514 MC research census.

This code never elevates SHADOW issuer-arithmetic to C4.17 PRIMARY MC.
Input JSONs are sanitized original GitHub Actions artifacts; no prices,
share counts, MC amounts, vendor payloads or credentials are persisted.
"""
from __future__ import annotations
import argparse,collections,hashlib,json
from pathlib import Path
from current_history_source_request import sha256_lines
ROOT=Path(__file__).resolve().parent
SCHEMA="XRAY_P0_SEC_ALPACA_514_MC_FOUR_ARTIFACT_JOIN_V1"
SOURCE="XRAY_PERSONAL_SEC_ALPACA_FULL_514_MC_FOUR_SHARD_SHADOW_V1"
def require(ok,msg):
    if not ok:raise ValueError("XRAY_514_MC_FOUR_JOIN:"+msg)
def blob(b):
    return hashlib.sha1(b"blob "+str(len(b)).encode()+b"\0"+b).hexdigest()

def combine(files,price_b,master_b,source_sha):
    p=json.loads(price_b);m=json.loads(master_b)
    expected=p.get("pass_symbols") or []
    require(p.get("asof_et")==m.get("asof_et")=="2026-10-09"
            and len(expected)==p.get("pass_count")==514
            and expected==sorted(set(expected))
            and sha256_lines(expected)==p.get("pass_hash")
            and set(expected).issubset(set(m.get("pass_symbols") or []))
            and all(q.get("execution")=="NONE" and
                    q.get("real_money")=="NO-GO" and
                    q.get("unknown_never_pass") is True for q in (p,m)),
            "SOURCE_CURRENT_CANONICAL_SCOPE_NOT_EXACT")
    require(type(files) is dict and set(files)=={0,1,2,3},
            "MISSING_MATRIX_JOB")
    psha=blob(price_b);msha=blob(master_b)
    outcome={}
    totals=collections.Counter()
    for shard in range(4):
        j=files[shard]
        cohort=expected[shard::4]
        require(j.get("schema")==SOURCE
                and j.get("asof_et")=="2026-10-09"
                and j.get("shard")==shard
                and j.get("shard_total")==4
                and j.get("source_scope_pass_count")==514
                and j.get("sampled_symbols")==cohort
                and j.get("sampled_count")==len(cohort)
                and j.get("price_source_git_blob_sha")==psha
                and j.get("master_source_git_blob_sha")==msha
                and j.get("source_price_pass_hash")==p.get("pass_hash")
                and j.get("full_514_PRIMARY_claim") is False,
                "SOURCE_SHARD_SYMBOLS_SHA_OR_PROOF_FALSE_"+str(shard))
        symbols=j.get("outcomes") or {}
        require(type(symbols) is dict and set(symbols)==set(cohort)
                and j.get("production_C417_PRIMARY_MC_created")==0
                and j.get("production_HISTORY_PASS_created")==0
                and j.get("AL_R92_created") is False
                and j.get("GO") is False
                and j.get("raw_vendor_OHLCV_SEC_share_counts_archived") is False
                and j.get("execution")=="NONE"
                and j.get("real_money")=="NO-GO",
                "SHARD_AUTHORITY_OR_SOURCE_SET_INVALID_"+str(shard))
        counted=collections.Counter()
        for symbol,row in symbols.items():
            require(type(row) is dict and
                    row.get("C417_PRIMARY") is False and
                    isinstance(row.get("status"),str)
                    and row["status"].startswith(("UNKNOWN_","SHADOW_"))
                    and symbol not in outcome,"UNAUTHORIZED_MC_SYMBOL_OR_DUPLICATE")
            counted[row["status"]]+=1
            outcome[symbol]={"status":row["status"],
                             "research_issuer_arithmetic_only":row["status"].startswith("SHADOW_"),
                             "C417_PRIMARY_MC":False}
        require(dict(counted)==j.get("status_counts"),
                "SHARD_CATEGORY_COUNT_NOT_SYMBOL_EXACT")
        totals.update(counted)
    require(set(outcome)==set(expected)
            and len(outcome)==sum(totals.values())==514
            and isinstance(source_sha,str) and len(source_sha)==40
            and all(c in "0123456789abcdef" for c in source_sha),
            "FULL_514_SET_OR_UPSTREAM_COMMIT_NOT_EXACT")
    return {"schema":SCHEMA,"asof_et":"2026-10-09",
            "source_workflow_main_commit_sha":source_sha,
            "price_git_blob_sha":psha,
            "master_git_blob_sha":msha,
            "stock_scope":514,"exact_shard_count":4,
            "measured_symbol_count":len(outcome),
            "unique_symbol_count":len(outcome),
            "classification_counts":dict(sorted(totals.items())),
            "unaccounted_symbols":[],
            "symbol_classifications":outcome,
            "status":"RESEARCH_FULL_514_MC_ISSUER_ARITHMETIC_PARTITION_VERIFIED_SHADOW",
            "SEC_issuer_share_classes_exact_asof_and_CA_PIT_proven":False,
            "independent_marketcap_current_asof_witness_proven":False,
            "market_data_unattended_rights_separately_attested":False,
            "raw_vendor_OHLCV_shares_MC_dollars_persisted":False,
            "C417_PRIMARY_MC_created":0,
            "canonical_HISTORY_PASS_created":0,
            "AL_R92_created":False,"GO":False,
            "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True}

def selftest(parts,pb,mb,sha):
    d=combine(parts,pb,mb,sha)
    require(d["measured_symbol_count"]==514
            and d["C417_PRIMARY_MC_created"]==0,"REAL_514_POSITIVE")
    b={i:json.loads(json.dumps(x)) for i,x in parts.items()}
    b[0]["sampled_symbols"]=b[0]["sampled_symbols"][1:]
    try:combine(b,pb,mb,sha)
    except ValueError:pass
    else:raise AssertionError("MISSING_MEMBER_FALSE_PASS")
    b={i:json.loads(json.dumps(x)) for i,x in parts.items()}
    b[3]["outcomes"][next(iter(b[3]["outcomes"]))]["C417_PRIMARY"]=True
    try:combine(b,pb,mb,sha)
    except ValueError:pass
    else:raise AssertionError("FAKE_PRIMARY_ACCEPTED")
    print("XRAY_514_MC_FOUR_JOIN_SELFTEST=PASS_REAL_POSITIVE_2_NEGATIVE_OPTIMIZER_SAFE")

def main():
    q=argparse.ArgumentParser()
    for i in range(4):
        q.add_argument("--shard"+str(i),type=Path,required=True)
    q.add_argument("--source-sha",required=True)
    q.add_argument("--out",type=Path)
    q.add_argument("--selftest",action="store_true")
    a=q.parse_args()
    parts={i:json.loads(getattr(a,"shard"+str(i)).read_text()) for i in range(4)}
    pb=(ROOT/"canonical_current_price_dv30.json").read_bytes()
    mb=(ROOT/"canonical_current_master_manifest.json").read_bytes()
    if a.selftest:return selftest(parts,pb,mb,a.source_sha)
    require(a.out is not None,"OUTPUT_REQUIRED")
    result=combine(parts,pb,mb,a.source_sha)
    a.out.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print("XRAY_514_MC_FOUR_SOURCE_JOIN="+result["status"])
    print("XRAY_514_MC_FOUR_COUNTS="+json.dumps(result["classification_counts"],sort_keys=True))
    print("XRAY_514_MC_FOUR_NO_PRIMARY=true")

if __name__=="__main__":main()
