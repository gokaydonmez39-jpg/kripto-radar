#!/usr/bin/env python3
"""C4.18 multi-source PIT / entitlement guard: advisory ONLY.

No network calls, credentials, trading, raw bars, PRIMARY elevation or R92.
Real evidence must be read from a PRIVATE local path; no data is committed.
All comparisons are source-local and return only reason codes / safe counts.
An advisory acceptance can NEVER activate C4.18 (separate policy authority).
"""
from __future__ import annotations
import argparse
import copy
import datetime as dt
import hashlib
import json
import math
import re
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parent
POLICY=ROOT/"source_successor_c418_proposal.json"
PROFILE=ROOT/"c418_multi_source_profile_v1.json"
SCHEMA="XRAY_C418_MULTI_SOURCE_EVIDENCE_V1"
REPORT="XRAY_C418_MULTI_SOURCE_GUARD_REPORT_V1"
SHA256=re.compile(r"^[a-f0-9]{64}$")
SHA1=re.compile(r"^[a-f0-9]{40}$")
PROVIDERS={"Bigdata","Massive","SEC_EDGAR","NASDAQ","Alpaca","Yahoo_AKShare_Eastmoney"}
ALLOWED_SOURCE_KINDS={
    "Bigdata":{"MC"},
    "Massive":{"MC","PRICE","HISTORY"},
    "Alpaca":{"PRICE","HISTORY"},
    "SEC_EDGAR":set(),
    "NASDAQ":set(),
    "Yahoo_AKShare_Eastmoney":{"PRICE","HISTORY"},
}
# Diagnostic limit, NOT a production/calibrated C4.18 threshold.
DIAGNOSTIC_MC_MAX_REL_DIFF=0.10
RIGHTS=("unattended_runner","non_display","derived_signals",
        "internal_retention","output_delivery")

def _date(s):
    if not isinstance(s,str): return None
    try:
        v=dt.date.fromisoformat(s)
        return v if v.isoformat()==s else None
    except (ValueError,TypeError): return None

def _number(x):
    return type(x) in (int,float) and math.isfinite(x) and x>0

def _sha(x,size=64):
    return isinstance(x,str) and bool((SHA256 if size==64 else SHA1).fullmatch(x))

def _git_blob_sha(data:bytes)->str:
    return hashlib.sha1(b"blob "+str(len(data)).encode()+bytes([0])+data).hexdigest()

def canonical_price_binding(asof,ticker,claimed_sha):
    """Accept only bytes of the actual current PRICE Git artifact and its ticker."""
    try:
        blob=(ROOT/"canonical_current_price_dv30.json").read_bytes()
        price=json.loads(blob)
        scope=price.get("pass_symbols")
        return bool(
            isinstance(scope,list) and all(isinstance(x,str) for x in scope)
            and len(scope)==len(set(scope))
            and type(price.get("pass_count")) is int
            and len(scope)==price["pass_count"]
            and ticker in scope and price.get("asof_et")==asof
            and _git_blob_sha(blob)==claimed_sha
        )
    except (OSError, ValueError, TypeError, AttributeError):
        return False

def policy_is_frozen(p):
    return bool(
        isinstance(p,dict)
        and p.get("schema")=="XRAY_SOURCE_SUCCESSOR_POLICY_PROPOSAL_V1"
        and p.get("effective_production_policy")=="C4.17"
        and p.get("activation_status")=="PROPOSED_NOT_ACTIVATED"
        and p.get("execution")=="NONE" and p.get("real_money")=="NO-GO"
        and p.get("unknown_never_pass") is True
        and p.get("can_create_PRIMARY") is False
        and p.get("can_register_R92") is False
        and p.get("explicit_source_promotion_authorized") is False
        and p.get("numeric_thresholds",{}).get("min_market_cap_usd")==2000000000
    )

def verified_upstream_evidence(attestation):
    """Require independent, cryptographically verifiable provider lineage.

    There is currently no independently audited and pinned trust root for
    issuer-share-class market-cap lineage in the repo. A vendor-provided
    'upstream_root' string or an ordinary SHA does not verify independence.
    Fail closed until such a trust root and signature verification exist.
    """
    return False

def blocked(reasons,observed=0):
    return {
        "schema":REPORT,"status":"DATA_BLOCKED",
        "reason_codes":sorted(set(reasons)),
        "observed_source_count":observed,
        "independent_mc_source_count":0,
        "declared_distinct_upstream_roots_count":0,
        "diagnostic_mc_agreement":False,
        "production_authority":False,"can_create_PRIMARY":False,
        "can_register_R92":False,"execution":"NONE","real_money":"NO-GO",
        "unknown_never_pass":True,"vendor_raw_data_exported":False,
    }

def validate(evidence, grants, policy, profile):
    """Strict, comparison-only validation. Grants are separate PRIVATE inputs.

    Grant self-assertions are NOT a verified legal entitlement: even a
    mechanically valid bundle remains strictly advisory (never PRIMARY).
    """
    if not policy_is_frozen(policy): return blocked(["POLICY_C417_NOT_FROZEN"])
    if not isinstance(profile,dict) or profile.get("schema")!="XRAY_C418_MULTI_SOURCE_PROFILE_V1":
        return blocked(["PROFILE_INVALID"])
    expected={
        "SEC_EDGAR":"OFFICIAL_PIT_IDENTITY",
        "NASDAQ":"EXCHANGE_IDENTITY",
        "Massive":"SHADOW_MC_OR_PRICE",
        "Alpaca":"SHADOW_HISTORY_OR_PRICE",
        "Bigdata":"BLOCKED_EXISTING_PRIMARY",
        "Yahoo_AKShare_Eastmoney":"UNLICENSED_SHADOW",
    }
    rows=profile.get("sources")
    if (not isinstance(rows,dict) or set(rows)!=set(expected)
        or any(not isinstance(rows[k],dict) or rows[k].get("role")!=v
               or rows[k].get("production_eligible") is not False
               for k,v in expected.items())):
        return blocked(["PROFILE_ROLES_TAMPERED"])
    if not isinstance(evidence,dict):return blocked(["NO_PRIVATE_LIVE_EVIDENCE"])
    if evidence.get("schema")!=SCHEMA:return blocked(["EVIDENCE_SCHEMA_INVALID"])
    asof=evidence.get("asof_et")
    if not _date(asof):return blocked(["ASOF_INVALID"])
    if not _sha(evidence.get("price_blob_sha"),40):return blocked(["PRICE_BLOB_SHA_INVALID"])
    ticker=evidence.get("symbol")
    cik=evidence.get("issuer_cik")
    share_class=evidence.get("share_class")
    if (not isinstance(ticker,str) or not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}",ticker)
        or not isinstance(cik,str) or not re.fullmatch(r"\d{10}",cik)
        or not isinstance(share_class,str) or not share_class.strip()):
        return blocked(["ISSUER_TICKER_CLASS_ID_INVALID"])
    if not canonical_price_binding(asof,ticker,evidence["price_blob_sha"]):
        return blocked(["CANONICAL_PRICE_BLOB_ASOF_MISMATCH"])
    identity=evidence.get("identity")
    if (not isinstance(identity,dict) or identity.get("source")!="SEC_EDGAR"
        or identity.get("exchange_source")!="NASDAQ"
        or identity.get("ticker")!=ticker or identity.get("issuer_cik")!=cik
        or identity.get("share_class")!=share_class
        or identity.get("exchange")!="NASDAQ"
        or not _date(identity.get("filed_on"))
        or identity["filed_on"]>asof
        or identity.get("pit_class_continuity_verified") is not True
        or identity.get("corporate_actions_class_exact") is not True):
        return blocked(["PIT_IDENTITY_CLASS_ACTIONS_UNPROVEN"])
    obs=evidence.get("observations")
    if not isinstance(obs,list):return blocked(["SOURCE_OBSERVATIONS_INVALID"])
    if not isinstance(grants,dict):return blocked(["PROVIDER_RIGHTS_NOT_ATTESTED"],len(obs))
    reasons=[]
    seen=set()
    groups={"MC":[],"PRICE":[],"HISTORY":[]}
    for row in obs:
        if not isinstance(row,dict):
            reasons.append("SOURCE_ROW_INVALID");continue
        provider=row.get("provider")
        kind=row.get("kind")
        if (provider not in PROVIDERS or kind not in groups
            or (provider,kind) in seen):
            reasons.append("UNKNOWN_DUPLICATE_OR_UNSUPPORTED_SOURCE");continue
        seen.add((provider,kind))
        if kind not in ALLOWED_SOURCE_KINDS[provider]:
            reasons.append("SOURCE_ROLE_INCORRECT");continue
        if (row.get("asof_et")!=asof or row.get("ticker")!=ticker
            or row.get("issuer_cik")!=cik or row.get("share_class")!=share_class
            or row.get("currency")!="USD"
            or row.get("price_blob_sha")!=evidence["price_blob_sha"]):
            reasons.append("SOURCE_ASOF_SCOPE_SHA_MISMATCH");continue
        root=row.get("upstream_root")
        if not isinstance(root,str) or not root or len(root)>128:
            reasons.append("UPSTREAM_LINEAGE_MISSING");continue
        # Rights must be separately attested per provider, never inferred
        # from successful API access or the source's own payload.
        grant=grants.get(provider)
        if (not isinstance(grant,dict)
            or not _sha(grant.get("rights_document_sha256"))
            or any(grant.get(k) is not True for k in RIGHTS)
            or not _date(grant.get("effective_from"))
            or not _date(grant.get("effective_to"))
            or not (grant["effective_from"]<=asof<=grant["effective_to"])):
            reasons.append("SOURCE_LICENSE_SCOPE_UNVERIFIED");continue
        if kind=="MC":
            if not _number(row.get("market_cap_usd")):
                reasons.append("MC_MEASUREMENT_INVALID");continue
        if kind=="PRICE":
            if not _number(row.get("close_usd")):
                reasons.append("PRICE_MEASUREMENT_INVALID");continue
        if kind=="HISTORY":
            if (row.get("last_260_official_sessions_exact") is not True
                or row.get("completed_52_weeks_exact") is not True
                or row.get("adjustment_basis_verified") is not True):
                reasons.append("HISTORY_260_52_ADJUSTMENT_UNPROVEN");continue
        groups[kind].append(row)
    if len(groups["MC"])<2:reasons.append("TWO_MC_SOURCES_REQUIRED")
    if not groups["PRICE"]:reasons.append("LICENSED_PRICE_REQUIRED")
    if not groups["HISTORY"]:reasons.append("LICENSED_HISTORY_REQUIRED")
    # MC vote-count inflation is forbidden when feeds share an origin.
    distinct={r["upstream_root"] for r in groups["MC"]}
    if len(groups["MC"])>=2 and len(distinct)<2:
        reasons.append("MC_SHARED_UPSTREAM_NOT_INDEPENDENT")
    if len(groups["MC"])>=2 and len(distinct)>=2 and not verified_upstream_evidence(
            evidence.get("independence_attestation")):
        reasons.append("UPSTREAM_INDEPENDENCE_UNATTESTED")
    agreement=False
    if len(groups["MC"])>=2 and len(distinct)>=2:
        vals=[r["market_cap_usd"] for r in groups["MC"]]
        diff=(max(vals)-min(vals))/max(vals)
        agreement=diff<=DIAGNOSTIC_MC_MAX_REL_DIFF
        if not agreement: reasons.append("MC_DIAGNOSTIC_CROSSCHECK_DISAGREEMENT")
    if reasons:
        result=blocked(reasons,len(obs))
        result["declared_distinct_upstream_roots_count"]=len(distinct)
        # Unverified strings must not be reported as independently proven MC
        # sources; keep verified count at zero.
        return result
    return {
        "schema":REPORT,
        "status":"SHADOW_CROSSCHECK_COMPLETE_NOT_PRIMARY",
        "reason_codes":["LEGAL_GRANTS_AND_SOURCE_EVIDENCE_REQUIRE_EXTERNAL_INDEPENDENT_REVIEW",
                        "C418_POLICY_NOT_ACTIVATED"],
        "observed_source_count":len(obs),
        "independent_mc_source_count":len(distinct),
        "diagnostic_mc_agreement":agreement,
        "production_authority":False,"can_create_PRIMARY":False,
        "can_register_R92":False,"execution":"NONE","real_money":"NO-GO",
        "unknown_never_pass":True,"vendor_raw_data_exported":False,
    }

def _selftest_impl(policy,profile,test_price_sha):
    assert policy_is_frozen(policy)
    assert validate(None,None,policy,profile)["status"]=="DATA_BLOCKED"
    e={
        "schema":SCHEMA,"asof_et":"2026-10-08","price_blob_sha":test_price_sha,
        "symbol":"TEST","issuer_cik":"0000123456","share_class":"CLASS_A",
        "identity":{"source":"SEC_EDGAR","exchange_source":"NASDAQ",
                    "ticker":"TEST","issuer_cik":"0000123456",
                    "share_class":"CLASS_A","exchange":"NASDAQ",
                    "filed_on":"2026-10-06","pit_class_continuity_verified":True,
                    "corporate_actions_class_exact":True},
        "observations":[]
    }
    def item(provider,kind,root,val=None):
        r={"provider":provider,"kind":kind,"upstream_root":root,
           "asof_et":e["asof_et"],"ticker":e["symbol"],
           "issuer_cik":e["issuer_cik"],"share_class":e["share_class"],
           "currency":"USD","price_blob_sha":e["price_blob_sha"]}
        if kind=="MC":r["market_cap_usd"]=val
        if kind=="PRICE":r["close_usd"]=val
        if kind=="HISTORY":r.update(last_260_official_sessions_exact=True,
            completed_52_weeks_exact=True,adjustment_basis_verified=True)
        return r
    # Unit-test values only; no market bars or licensed observations.
    e["observations"]=[item("Bigdata","MC","VENDOR_B",2100000000),
                       item("Massive","MC","VENDOR_M",2050000000),
                       item("Massive","PRICE","VENDOR_M",20),
                       item("Alpaca","HISTORY","VENDOR_A")]
    grant={name:dict(rights_document_sha256="a"*64,
                     effective_from="2026-01-01",effective_to="2026-12-31",
                     unattended_runner=True,non_display=True,
                     derived_signals=True,internal_retention=True,
                     output_delivery=True)
           for name in ("Bigdata","Massive","Alpaca")}
    ok=validate(e,grant,policy,profile)
    assert ok["status"]=="DATA_BLOCKED",ok
    assert "UPSTREAM_INDEPENDENCE_UNATTESTED" in ok["reason_codes"],ok
    assert ok["independent_mc_source_count"]==0
    assert ok["declared_distinct_upstream_roots_count"]==2
    assert ok["can_register_R92"] is False and ok["can_create_PRIMARY"] is False
    failures=[
       ("LICENSE",lambda a,g:g["Alpaca"].update(non_display=False),
        "SOURCE_LICENSE_SCOPE_UNVERIFIED"),
       ("SHARED_ROOT",lambda a,g:a["observations"][1].update(upstream_root="VENDOR_B"),
        "MC_SHARED_UPSTREAM_NOT_INDEPENDENT"),
       ("ASOF",lambda a,g:a["observations"][1].update(asof_et="2026-10-07"),
        "SOURCE_ASOF_SCOPE_SHA_MISMATCH"),
       ("PRICE_BLOB",lambda a,g:a["observations"][2].update(price_blob_sha="b"*40),
        "SOURCE_ASOF_SCOPE_SHA_MISMATCH"),
       ("CLASS",lambda a,g:a["observations"][0].update(share_class="CLASS_B"),
        "SOURCE_ASOF_SCOPE_SHA_MISMATCH"),
       ("HISTORY",lambda a,g:a["observations"][3].update(completed_52_weeks_exact=False),
        "HISTORY_260_52_ADJUSTMENT_UNPROVEN"),
       ("MC_DISAGREE",lambda a,g:a["observations"][0].update(market_cap_usd=4000000000),
        "MC_DIAGNOSTIC_CROSSCHECK_DISAGREEMENT"),
       ("PIT",lambda a,g:a["identity"].update(filed_on="2026-10-09"),
        "PIT_IDENTITY_CLASS_ACTIONS_UNPROVEN"),
       ("DUP",lambda a,g:a["observations"].append(copy.deepcopy(a["observations"][0])),
        "UNKNOWN_DUPLICATE_OR_UNSUPPORTED_SOURCE"),
       ("UNLICENSED",lambda a,g:g.pop("Massive"),
        "SOURCE_LICENSE_SCOPE_UNVERIFIED"),
       ("SHARES",lambda a,g:a["identity"].update(corporate_actions_class_exact=False),
        "PIT_IDENTITY_CLASS_ACTIONS_UNPROVEN"),
       ("ROLE_ALPACA_MC",lambda a,g:a["observations"][1].update(provider="Alpaca"),
        "SOURCE_ROLE_INCORRECT"),
       ("ROLE_NASDAQ_PRICE",lambda a,g:a["observations"][2].update(provider="NASDAQ"),
        "SOURCE_ROLE_INCORRECT"),
    ]
    for name,mutate,reason in failures:
        z=copy.deepcopy(e);g=copy.deepcopy(grant);mutate(z,g)
        result=validate(z,g,policy,profile)
        assert result["status"]=="DATA_BLOCKED",(name,result)
        assert reason in result["reason_codes"],(name,result)
        assert result["can_create_PRIMARY"] is False
        assert result["can_register_R92"] is False
    tampered=copy.deepcopy(profile)
    tampered["sources"]["Massive"]["role"]="PRIMARY"
    assert "PROFILE_ROLES_TAMPERED" in validate(e,grant,policy,tampered)["reason_codes"]
    print("XRAY_C418_MULTI_SOURCE_SELFTEST=PASS_STRUCTURAL_SOURCE_COMPARISON_REQUIRES_ATTESTATION_14_NEGATIVE_NO_PRIMARY_NO_R92")

def selftest(policy,profile):
    global ROOT
    original=ROOT
    with tempfile.TemporaryDirectory(prefix="xray-c418-price-sha-fixture-") as tmp:
        try:
            ROOT=Path(tmp)
            blob=json.dumps({
                "asof_et":"2026-10-08",
                "pass_symbols":["TEST"],"pass_count":1
            },sort_keys=True).encode()
            (ROOT/"canonical_current_price_dv30.json").write_bytes(blob)
            _selftest_impl(policy,profile,_git_blob_sha(blob))
        finally:
            ROOT=original

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--selftest",action="store_true")
    ap.add_argument("--manifest",type=Path)
    ap.add_argument("--private-rights",type=Path)
    ap.add_argument("--out",type=Path)
    args=ap.parse_args()
    policy=json.loads(POLICY.read_text())
    profile=json.loads(PROFILE.read_text())
    if args.selftest:
        selftest(policy,profile)
        return
    evidence=None;rights=None
    if args.manifest and args.private_rights:
        # A public repo manifest would be an unsafe storage location.
        for path in (args.manifest,args.private_rights):
            if path.resolve().is_relative_to(ROOT.parent.resolve()):
                raise SystemExit("XRAY_C418_VENDOR_EVIDENCE_MUST_NOT_BE_PUBLIC_GITHUB")
        evidence=json.loads(args.manifest.read_text())
        rights=json.loads(args.private_rights.read_text())
    result=validate(evidence,rights,policy,profile)
    if args.out:
        args.out.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print("XRAY_C418_MULTI_SOURCE_STATUS="+result["status"])
    print("XRAY_C418_MULTI_SOURCE_REASONS="+",".join(result["reason_codes"]))
    print("XRAY_C418_MULTI_SOURCE_PRODUCTION_AUTHORITY=false")
    if result["status"]=="DATA_BLOCKED":
        raise SystemExit(2)

if __name__=="__main__":
    main()
