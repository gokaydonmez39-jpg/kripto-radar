#!/usr/bin/env python3
"""Bounded exact-ASOF, SHA-verified SECONDARY SEC CIK discovery for research.

Consumes already-completed same-run 414 research cohort. An independently
published, SHA-manifest-pinned mirror helps triage official SEC transport
outages; it is NEVER SEC-original confirmation, MC PIT, price, R92 or GO.
"""
from __future__ import annotations
import argparse
from collections import Counter
import datetime as dt
import json
from pathlib import Path
import re

from alpaca_full_universe_asof_sip_availability import sha
from personal_sec_current_cik_shadow import validate_route
from sec_mirror_cik_shadow import discover, fetch

SCHEMA="XRAY_PERSONAL_SEC_ASOF_MIRROR_414_DISCOVERY_RESEARCH_V1"
FOUND="MIRROR_EXACT_ASOF_SEC_TICKER_CIK_DISCOVERY_NOT_OFFICIAL_ATTESTATION"
NOT_FOUND="UNKNOWN_MIRROR_SNAPSHOT_NO_NASDAQ_CIK"
UNAVAILABLE="UNKNOWN_MIRROR_SOURCE_NOT_VERIFIED"
ROOT=Path(__file__).resolve().parent
def need(ok,why):
    if not ok:raise ValueError("XRAY_PERSONAL_SEC_MIRROR_"+why)

def measure(causal,now,request=fetch):
    asof,names=validate_route(causal,now)
    # The conditional backup must not claim complete primary RTH or MC.
    need(causal.get("rth30_partial_research_never_primary") is True
         and causal.get("rth30_partial_missing_slot_high_research_only_count")
            <=len(names)
         and causal.get("rth30_strict_complete_slot_lower_bound_observed")+
            causal.get("rth30_partial_missing_slot_high_research_only_count")==len(names)
         and causal.get("rth30_data_unknown_count")>=
            causal.get("rth30_partial_missing_slot_high_research_only_count"),
         "EXACT_RESEARCH_ONLY_RTH_SCOPE")
    flags=dict.fromkeys(names,UNAVAILABLE)
    found={};source=None;failure=None
    try:
        evidence=discover(asof,names,request=request)
        source=evidence.get("source_commit")
        found=evidence.get("ciK_discovery_only")
        need(evidence.get("status")=="EXACT_ASOF_CIK_DISCOVERY_ONLY"
             and evidence.get("snapshot_date")==asof
             and evidence.get("source_repository")=="TylerJForstrom/Stock-Data"
             and type(source) is str and re.fullmatch(r"[0-9a-f]{40}",source)
             and type(evidence.get("source_sha256")) is str
             and re.fullmatch(r"[0-9a-f]{64}",evidence["source_sha256"])
             and type(found) is dict and set(found).issubset(names)
             and len(found)==evidence.get("ciK_discovered_count")
             and evidence.get("unknown_total")==len(names)
             and all(type(v) is str and
                     re.fullmatch(r"[0-9]{10}",v) for v in found.values()),
             "MIRROR_MANIFEST_AND_SHA_PROVENANCE")
        flags={s:(FOUND if s in found else NOT_FOUND) for s in names}
    except (OSError,RuntimeError,ValueError,TypeError,KeyError,
            json.JSONDecodeError):
        # No stale/future/mismatched third-party mirror can promote a symbol.
        source=None;found={};failure="MIRROR_UNAVAILABLE_OR_SHA_ASOF_INVALID"
        flags=dict.fromkeys(names,UNAVAILABLE)
    counts=dict(sorted(Counter(flags.values()).items()))
    need(set(flags)==set(names) and sum(counts.values())==len(names)
         and set(found)=={s for s in names if flags[s]==FOUND},
         "EXACT_CLASSIFICATION_PARTITION")
    return {
        "schema":SCHEMA,"asof_et":asof,
        "source_causal_cohort_sha256":sha(names),"scope_count":len(names),
        "mirror_source_repository":"TylerJForstrom/Stock-Data",
        "mirror_source_commit":source,
        "mirror_asof_pinned":bool(source),
        "mirror_status":failure or "EXACT_ASOF_SHA_VERIFIED_SECONDARY_DISCOVERY",
        "mirror_found_count":len(found),
        "classifications":dict(sorted(flags.items())),
        "classification_counts":counts,
        "ciK_secondary_discovery_only":dict(sorted(found.items())),
        "independent_official_sec_lookup_pass":False,
        "exchange_listing_asof_pit_attested":False,
        "issuer_class_shares_current_pit_attested":False,
        "market_cap_2b_attested":False,
        "official_c417_primary_price_dv30_attested":False,
        "technical_watch_generated_here":False,
        "registered_R92_count":0,
        "iphone_delivery_receipt_attested":False,
        "raw_vendor_ohlcv_persisted":False,
        "source_rights_not_inferred":True,
        "canonical_files_mutated":False,
        "execution":"NONE","real_money":"NO-GO",
    }

def selftest():
    from copy import deepcopy
    asof="2026-10-15"
    now=dt.datetime(2026,10,15,23,30,tzinfo=dt.timezone.utc)
    names=["AAPL","MSFT"]
    causal={
        "schema":"XRAY_PERSONAL_SIX_GATE_CAUSAL_BREAKER_V1",
        "asof_et":asof,"execution":"NONE","real_money":"NO-GO",
        "no_canonical_mutations":True,"no_vendor_ohlcv_persisted":True,
        "issuer_class_mc_current_attested":False,
        "c417_price_dv30_primary_attested":False,
        "registered_r92_count":0,
        "next_gate_mc_sec_research_only_symbols":names,
        "rth30_lower_bound_observed":2,"rth30_lower_bound_sha256":sha(names),
        "rth30_partial_missing_slot_high_research_only_count":2,
        "rth30_strict_complete_slot_lower_bound_observed":0,
        "rth30_partial_research_never_primary":True,
        "rth30_data_unknown_count":2
    }
    from hashlib import sha256
    raw=b'{"ticker":"AAPL","cik":320193,"exchange":"Nasdaq"}\n'
    manifest={
        "snapshot_date":asof,"last_success":{"sec_company_tickers_exchange":asof},
        "files":[{"name":"sec_company_tickers_exchange.jsonl",
                  "bytes":len(raw),"sha256":sha256(raw).hexdigest()}]}
    rev="a"*40
    prefix="https://raw.githubusercontent.com/TylerJForstrom/Stock-Data/"+rev+"/data/symbols/current/"
    def fake(url):
        if "/commits?" in url:return json.dumps([{"sha":rev}]).encode()
        if url==prefix+"manifest.json":return json.dumps(manifest).encode()
        if url==prefix+"sec_company_tickers_exchange.jsonl":return raw
        raise ValueError("INVALID_URL")
    good=measure(causal,now,fake)
    need(good["mirror_found_count"]==1
         and good["ciK_secondary_discovery_only"]=={"AAPL":"0000320193"}
         and good["classification_counts"]=={FOUND:1,NOT_FOUND:1}
         and good["market_cap_2b_attested"] is False
         and good["registered_R92_count"]==0
         and good["technical_watch_generated_here"] is False,
         "EXACT_ASOF_POSITIVE_NO_MC")
    def fail(_):raise ValueError("BLOCK")
    bad=measure(causal,now,fail)
    need(bad["mirror_found_count"]==0 and
         bad["classification_counts"]=={UNAVAILABLE:2}
         and not bad["mirror_asof_pinned"],
         "BLOCKED_MIRROR_NEVER_PASS")
    def altered(url):
        if url==prefix+"sec_company_tickers_exchange.jsonl":return raw+b"BAD"
        return fake(url)
    bad=measure(causal,now,altered)
    need(bad["classification_counts"]=={UNAVAILABLE:2},
         "MANIFEST_SHA_MISMATCH_NEVER_PASS")
    def future(url):
        if url==prefix+"manifest.json":
            return json.dumps(dict(manifest,snapshot_date="2026-10-16")).encode()
        return fake(url)
    bad=measure(causal,now,future)
    need(bad["classification_counts"]=={UNAVAILABLE:2},
         "FUTURE_SNAPSHOT_NEVER_PASS")
    for mutant in (
        lambda p:p.update(rth30_lower_bound_sha256="a"*64),
        lambda p:p.update(issuer_class_mc_current_attested=True),
        lambda p:p.update(asof_et="2026-10-14"),
        lambda p:p.update(rth30_partial_research_never_primary=False),
        lambda p:p.update(registered_r92_count=1),
    ):
        broken=deepcopy(causal);mutant(broken)
        try:measure(broken,now,fake)
        except ValueError:pass
        else:raise AssertionError("FORGED_CAUSAL_SCOPE_ACCEPTED")
    print("XRAY_SEC_MIRROR_414_SELFTEST=PASS_EXACT_ASOF_SHA_7_NEGATIVES_ZERO_MC_R92")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--causal",type=Path)
    p.add_argument("--out",type=Path)
    opts=p.parse_args()
    if opts.selftest:selftest();return
    need(opts.causal is not None and opts.causal.is_file()
         and opts.out is not None and not opts.out.resolve().is_relative_to(ROOT.parent.resolve()),
         "EPHEMERAL_SOURCE_OUTPUT_ONLY")
    causal=json.loads(opts.causal.read_text())
    out=measure(causal,dt.datetime.now(dt.timezone.utc))
    opts.out.write_text(json.dumps(out,sort_keys=True,indent=2)+"\n")
    print("XRAY_SEC_MIRROR_414="+json.dumps({
        "asof_et":out["asof_et"],"scope":out["scope_count"],
        "found_secondary":out["mirror_found_count"],
        "mirror_state":out["mirror_status"],
        "MC":False,"R92":0,"execution":"NONE"},sort_keys=True))
if __name__=="__main__":main()
