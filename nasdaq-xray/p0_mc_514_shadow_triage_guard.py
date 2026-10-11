#!/usr/bin/env python3
"""Strict source-locked 514 SEC+Alpaca MC shadow risk triage; NEVER PRIMARY.

Source inputs are the original 2026-10-09 four separate Actions shard JSONs,
the original exactly-joined GitHub Actions JSON and current frozen PRICE/MASTER.
Only sanitized classification flags, dates-as-ages, and ticker names are saved.
Raw vendor price, shares and calculated market caps are never persisted.
"""
from __future__ import annotations
import argparse, collections, copy, hashlib, json
from pathlib import Path

ASOF = "2026-10-09"
PRICE_BLOB = "6f3f68fff0897d68f200ad3621c51a5071494714"
MASTER_BLOB = "828c21436a836b69fe5084387e1c54446c7b5075"
JOIN_SCHEMA = "XRAY_P0_SEC_ALPACA_514_MC_FOUR_ARTIFACT_JOIN_V1"
SHARD_SCHEMA = "XRAY_PERSONAL_SEC_ALPACA_FULL_514_MC_FOUR_SHARD_SHADOW_V1"
S_SHADOW = "SHADOW_SEC_PIT_AND_SIP_CLOSE_ARITHMETIC_VERIFIED_CLASS_CA_UNPROVEN"
S_UNKNOWN = "UNKNOWN_SEC_DIMENSIONAL_CLASS_OR_PIT_SHARES"
OUT_SCHEMA = "XRAY_P0_514_SHADOW_TRIAGE_ORIGINAL_FOUR_SHARD_V1"
DIRECT = frozenset("ASND CBSH CCC CMCSA DFTX ECHO FISV HON INDV IRTC MIDD MRX TRI".split())
ACQUIRER = frozenset("ASST BKR BNTX CHTR CORZ GMAB HBAN IESC LGND NBIX NXST RGEN RGLD SNY SOUN SWKS USAR WFRD".split())
def require(ok,code):
    if not ok:
        raise ValueError("XRAY_MC514_TRIAGE:"+code)
def gitblob(raw):
    return hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()
def symbols_hash(items):
    return hashlib.sha256("\n".join(items).encode("utf-8")).hexdigest()
def count(items):
    return len(items)
def validate(union, shards, price_b, master_b):
    p=json.loads(price_b);m=json.loads(master_b)
    expected=p.get("pass_symbols")
    require(gitblob(price_b)==PRICE_BLOB and gitblob(master_b)==MASTER_BLOB,
            "SOURCE_FROZEN_BLOB_DRIFT")
    require(p.get("asof_et")==m.get("asof_et")==ASOF
            and type(expected) is list and expected==sorted(set(expected))
            and count(expected)==p.get("pass_count")==514
            and symbols_hash(expected)==p.get("pass_hash")
            and set(expected).issubset(set(m.get("pass_symbols") or []))
            and all(x.get("unknown_never_pass") is True and
                    x.get("execution")=="NONE" and x.get("real_money")=="NO-GO"
                    for x in (p,m)), "EXACT_PRICE_MASTER_SCOPE_DRIFT")
    require(type(shards) is dict and set(shards)=={0,1,2,3},
            "SOURCE_SHARD_MATRIX_INCOMPLETE")
    original=union.get("symbol_classifications")
    require(union.get("schema")==JOIN_SCHEMA
            and union.get("asof_et")==ASOF
            and union.get("stock_scope")==union.get("unique_symbol_count")
                 ==union.get("measured_symbol_count")==514
            and union.get("price_git_blob_sha")==PRICE_BLOB
            and union.get("master_git_blob_sha")==MASTER_BLOB
            and union.get("C417_PRIMARY_MC_created")==0
            and union.get("AL_R92_created") is False
            and union.get("GO") is False
            and union.get("raw_vendor_OHLCV_shares_MC_dollars_persisted") is False
            and type(original) is dict and set(original)==set(expected),
            "ORIGINAL_UNION_MUTATION")
    rows={}
    for shard in range(4):
        d=shards[shard]
        cohort=expected[shard::4]
        require(d.get("schema")==SHARD_SCHEMA and
                d.get("asof_et")==ASOF and d.get("shard")==shard
                and d.get("shard_total")==4
                and d.get("sampled_symbols")==cohort
                and d.get("sampled_count")==len(cohort)
                and d.get("price_source_git_blob_sha")==PRICE_BLOB
                and d.get("master_source_git_blob_sha")==MASTER_BLOB
                and d.get("production_C417_PRIMARY_MC_created")==0
                and d.get("production_HISTORY_PASS_created")==0
                and d.get("AL_R92_created") is False and d.get("GO") is False
                and d.get("raw_vendor_OHLCV_SEC_share_counts_archived") is False
                and d.get("execution")=="NONE" and d.get("real_money")=="NO-GO",
                "SHARD_SOURCE_OR_SAFETY_DRIFT_"+str(shard))
        source=d.get("outcomes")
        require(type(source) is dict and set(source)==set(cohort),
                "SHARD_SYMBOL_SET_DRIFT_"+str(shard))
        local=collections.Counter()
        for symbol,rec in source.items():
            require(symbol not in rows and type(rec) is dict and
                    rec.get("C417_PRIMARY") is False and
                    rec.get("status") in (S_SHADOW,S_UNKNOWN),
                    "SHARD_ROW_FAKE_PRIMARY_OR_DUPLICATE")
            cls=rec["status"]
            other=original.get(symbol)
            require(type(other) is dict and
                    other.get("status")==cls and
                    other.get("C417_PRIMARY_MC") is False and
                    other.get("research_issuer_arithmetic_only") is (cls==S_SHADOW),
                    "ORIGINAL_JOIN_ROW_CONTRADICTION")
            age=rec.get("sec_vintage_age_days")
            above=rec.get("above_2b_derived_issuer_shadow")
            if cls==S_SHADOW:
                require(type(above) is bool and type(age) is int and 0<=age<=120,
                        "SHADOW_INVALID_AGE_OR_BOOLEAN")
            else:
                require(above is None and age is None,
                        "UNKNOWN_MUST_HAVE_NO_MC_OR_AGE_PROOF")
            local[cls]+=1
            rows[symbol]={"source_status":cls,
                          "issuer_unadjusted_arithmetic_above_2b_only":above,
                          "SEC_share_vintage_age_days":age,
                          "C417_PRIMARY_MC":False}
        require(dict(sorted(local.items()))==d.get("status_counts"),
                "SHARD_COUNT_NOT_RECONCILED_"+str(shard))
    require(set(rows)==set(expected)
            and len(rows)==514
            and set(DIRECT).isdisjoint(ACQUIRER)
            and len(DIRECT)==13 and len(ACQUIRER)==18
            and (DIRECT|ACQUIRER).issubset(set(rows)),
            "FULL_SCOPE_OR_CA_ROLE_DRIFT")
    by_status=collections.Counter(x["source_status"] for x in rows.values())
    require(by_status[S_SHADOW]==346 and by_status[S_UNKNOWN]==168
            and dict(sorted(by_status.items()))==union.get("classification_counts"),
            "346_168_ORIGINAL_COUNTS_DRIFT")
    confirmed=[s for s,x in rows.items() if x["source_status"]==S_SHADOW]
    arithmetic_high=sorted(s for s in confirmed if rows[s]["issuer_unadjusted_arithmetic_above_2b_only"] is True)
    arithmetic_low=sorted(s for s in confirmed if rows[s]["issuer_unadjusted_arithmetic_above_2b_only"] is False)
    ages={k:[] for k in ("0_30","31_60","61_90","91_120")}
    for symbol in confirmed:
        age=rows[symbol]["SEC_share_vintage_age_days"]
        key="0_30" if age<=30 else "31_60" if age<=60 else "61_90" if age<=90 else "91_120"
        ages[key].append(symbol)
    for symbols in ages.values():symbols.sort()
    direct_unknown=sorted(s for s in DIRECT if rows[s]["source_status"]==S_UNKNOWN)
    acquirer_unknown=sorted(s for s in ACQUIRER if rows[s]["source_status"]==S_UNKNOWN)
    require(len(arithmetic_high)+len(arithmetic_low)==346
            and sum(map(len,ages.values()))==346
            and len(direct_unknown)+len(acquirer_unknown)==13,
            "TRIAGE_DERIVED_PARTITION_INCOMPLETE")
    return {
        "schema":OUT_SCHEMA,"asof_et":ASOF,
        "source_four_shard_run_id":38183058048,
        "source_four_join_run_id":38183357135,
        "price_source_git_blob_sha":PRICE_BLOB,
        "master_source_git_blob_sha":MASTER_BLOB,
        "original_full_unique_scope":514,"original_shadow_count":346,
        "original_unknown_count":168,
        "original_issuer_arithmetic_unadjusted_above_floor_only_count":len(arithmetic_high),
        "original_issuer_arithmetic_unadjusted_below_floor_only_count":len(arithmetic_low),
        "unadjusted_below_floor_symbols":arithmetic_low,
        "SEC_share_vintage_age_bucket_counts":{k:len(v) for k,v in ages.items()},
        "SEC_vintage_over90day_symbols":ages["91_120"],
        "CA_direct13_shadow_count":13-len(direct_unknown),
        "CA_direct13_unknown_symbols":direct_unknown,
        "CA_acquirer18_shadow_count":18-len(acquirer_unknown),
        "CA_acquirer18_unknown_symbols":acquirer_unknown,
        "CA31_total":31,
        "CA31_issuer_asof_reconciliation_complete":False,
        "class_specific_tradable_security_shares_confirmed":False,
        "independent_pit_issuer_market_cap_confirmed":False,
        "later_corpa_issuance_repurchase_ADS_adjustment_proven":False,
        "arithmetic_boolean_does_not_prove_C417_MC_pass_or_fail":True,
        "source_excluded_raw_shares_prices_MC_USD":True,
        "C417_PRIMARY_MC_created":0,"canonical_HISTORY_PASS_created":0,
        "R92_created":False,"GO":False,
        "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True
    }

def selftest(union,shards,pb,mb):
    result=validate(union,shards,pb,mb)
    require(result["original_shadow_count"]==346 and result["original_unknown_count"]==168
            and result["C417_PRIMARY_MC_created"]==0 and result["GO"] is False,
            "REAL_POSITIVE")
    def reject(name,mutator):
        b=copy.deepcopy(shards); u=copy.deepcopy(union)
        mutator(u,b)
        try:validate(u,b,pb,mb)
        except ValueError:return
        raise AssertionError("XRAY_MC514_TRIAGE_FALSE_ACCEPT:"+name)
    reject("FAKE_PRIMARY",lambda u,b:b[0]["outcomes"][b[0]["sampled_symbols"][0]].update({"C417_PRIMARY":True}))
    reject("SHARD_TICKER_LOST",lambda u,b:b[1]["outcomes"].pop(b[1]["sampled_symbols"][0]))
    reject("UNION_STATUS_FORGED",lambda u,b:u["symbol_classifications"][next(iter(u["symbol_classifications"]))].update({"status":"MC_PASS_PRIMARY"}))
    reject("LOSS_OF_BOOLEAN_PROOF",lambda u,b:next(x for x in b[0]["outcomes"].values() if x["status"]==S_SHADOW).update({"above_2b_derived_issuer_shadow":None}))
    reject("INVALID_AGE",lambda u,b:next(x for x in b[0]["outcomes"].values() if x["status"]==S_SHADOW).update({"sec_vintage_age_days":121}))
    reject("CORRUPT_COUNT",lambda u,b:b[3].update({"sampled_count":500}))
    reject("FAKE_R92",lambda u,b:u.update({"AL_R92_created":True}))
    reject("FAKE_SHARD_GO",lambda u,b:b[2].update({"GO":True}))
    print("XRAY_MC514_SHADOW_TRIAGE_SELFTEST=PASS_1_REAL_POSITIVE_8_NEGATIVE_OPTIMIZER_SAFE")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--union",type=Path,required=True)
    for i in range(4):p.add_argument("--shard"+str(i),type=Path,required=True)
    p.add_argument("--price",type=Path,default=Path(__file__).resolve().parent/"canonical_current_price_dv30.json")
    p.add_argument("--master",type=Path,default=Path(__file__).resolve().parent/"canonical_current_master_manifest.json")
    p.add_argument("--out",type=Path)
    p.add_argument("--selftest",action="store_true")
    a=p.parse_args()
    union=json.loads(a.union.read_text())
    shards={i:json.loads(getattr(a,"shard"+str(i)).read_text()) for i in range(4)}
    pb=a.price.read_bytes();mb=a.master.read_bytes()
    if a.selftest:return selftest(union,shards,pb,mb)
    require(a.out is not None,"OUTPUT_REQUIRED")
    result=validate(union,shards,pb,mb)
    a.out.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print("XRAY_MC514_SHADOW_TRIAGE_COUNTS="+json.dumps({
        "above":result["original_issuer_arithmetic_unadjusted_above_floor_only_count"],
        "below":result["original_issuer_arithmetic_unadjusted_below_floor_only_count"],
        "age":result["SEC_share_vintage_age_bucket_counts"]},sort_keys=True))
    print("XRAY_MC514_SHADOW_TRIAGE_PRIMARY=0_NO_GO")

if __name__=="__main__":main()
