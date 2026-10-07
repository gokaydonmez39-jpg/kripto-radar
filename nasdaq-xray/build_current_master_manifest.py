#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,os,re
from pathlib import Path

ROOT=Path(__file__).resolve().parent
INPUT=Path(os.getenv("XRAY_MASTER_STATE",str(ROOT/"canonical_current_full_state.json")))
OUT=Path(os.getenv("XRAY_MASTER_MANIFEST",str(ROOT/"canonical_current_master_manifest.json")))
TASK="6a825366222081918997094d76e6ae46"
ALLOWED_EXCLUSION_REASONS={
  "TEST_ISSUE","ETF","NEXTSHARES","WARRANT","RIGHT","UNIT",
  "PREFERRED","DEBT","ETN","FUND","WHEN_ISSUED","SPAC_BLANK_CHECK","POST_ASOF_LISTING"
}
FULL_IDENTITY_AUTHORITIES={
  "FULL_IDENTITY_NO_PREFILTER",
  "CANONICAL_FROZEN_FULL_IDENTITY_SAME_ASOF",
  "IMMUTABLE_EXACT_ASOF_MEMBERSHIP_SNAPSHOT_NO_MARKET_DECISIONS",
}

def valid_full_identity_authority(dm):
    return bool(isinstance(dm,dict) and dm.get("full_identity") is True and dm.get("authority") in FULL_IDENTITY_AUTHORITIES)

def blob_sha(p):
    b=p.read_bytes()
    return hashlib.sha1(f"blob {len(b)}\0".encode()+b).hexdigest()

def hash_lines(xs):
    return hashlib.sha256("\n".join(xs).encode()).hexdigest()

FOOTER_RE=re.compile(r"^File Creation Time:\s*(\d{2})(\d{2})(\d{4})")
SPAC_SUSPECT_RE=re.compile(r"\bacquisition\b|\bspac\b|\bblank[ -]?check\b|\bcapital\s+corp(?:oration)?\.?\s+(?:[IVXLCDM]+|\d+)\s*-\s*class\s+a\s+ordinary\s+shares?\b",re.I)
def official_footer_asof_exact(footer,asof):
    m=FOOTER_RE.match(str(footer or "").strip())
    if not m:
        return False
    mm,dd,yyyy=m.groups()
    return f"{yyyy}-{mm}-{dd}"==str(asof or "")

def valid_sec_spac_proof_binding(dm,asof):
    try:
        n=int(dm.get("sec_spac_proof_count",0) or 0)
        path=str(dm.get("sec_spac_proof_path") or "")
        sha=str(dm.get("sec_spac_proof_blob_sha") or "")
        if n==0:
            return not path and not sha
        if not path or not sha:
            return False
        p=ROOT.parent/path
        if not p.exists() or blob_sha(p)!=sha:
            return False
        j=json.loads(p.read_text())
        proofs=j.get("proofs") or {}
        if not (
          j.get("schema")=="XRAY_MASTER_SEC_SPAC_PROOF_V1"
          and j.get("execution")=="NONE" and j.get("real_money")=="NO-GO"
          and j.get("unknown_never_pass") is True
          and j.get("authority")=="SEC_EDGAR_SIC_6770_EXACT_ASOF"
          and j.get("applicability")=="EXACT_ASOF_ONLY_NO_FORWARD_CARRY"
          and j.get("asof_et")==asof
          and isinstance(proofs,dict) and len(proofs)==n
        ):
            return False
        for row in proofs.values():
            if not isinstance(row,dict) or int(row.get("sic",-1))!=6770:
                return False
            if row.get("same_asof_revalidated_without_sec_network") is True:
                if row.get("revalidation_semantics")!="PRIOR_SEC_SIC6770_WITHIN_120D_PLUS_SAME_ASOF_NASDAQ_SPAC_IDENTITY;NO_ALPHA_PASS":
                    return False
                source=str(row.get("source_url") or "")
                evidence=str(row.get("evidence_date") or "")
                footer=str(row.get("same_asof_nasdaq_directory_footer") or "")
                if not source.startswith("https://www.sec.gov/") or not re.fullmatch(r"20\d{2}-\d{2}-\d{2}",evidence) or evidence>asof:
                    return False
                try:
                    from datetime import datetime
                    age=(datetime.fromisoformat(asof)-datetime.fromisoformat(evidence)).days
                    if age<0 or age>120 or not official_footer_asof_exact(footer,asof):
                        return False
                except Exception:
                    return False
                current_name=str(row.get("same_asof_nasdaq_security_name") or "")
                industry=str(row.get("same_asof_nasdaq_screener_industry") or "")
                if not (
                  SPAC_SUSPECT_RE.search(current_name)
                  or industry.strip().lower()=="blank checks"
                ):
                    return False
        return True
    except Exception:
        return False


def valid_asof_identity_proof_binding(dm,asof):
    try:
        path=str(dm.get("asof_identity_proof_path") or "")
        sha=str(dm.get("asof_identity_proof_blob_sha") or "")
        counts=dm.get("asof_identity_proof_counts") or {}
        if not path or not sha:
            return False
        p=ROOT.parent/path
        if not p.exists() or blob_sha(p)!=sha:
            return False
        j=json.loads(p.read_text())
        expected={k:len(j.get(k) or {}) for k in ("restore_to_asof","remove_from_asof","operating_overrides")}
        return bool(
          j.get("schema")=="XRAY_MASTER_ASOF_IDENTITY_PROOF_V1"
          and j.get("execution")=="NONE" and j.get("real_money")=="NO-GO"
          and j.get("unknown_never_pass") is True
          and j.get("authority")=="NASDAQTRADER_SEC_EXACT_ASOF_IDENTITY_RECONCILIATION"
          and j.get("applicability")=="EXACT_ASOF_ONLY_NO_FORWARD_CARRY"
          and j.get("asof_et")==asof
          and counts==expected
        )
    except Exception:
        return False

def main():
    s=json.loads(INPUT.read_text())
    assert s["schema"]=="XRAY_NASDAQ_SCREENER_SINA_V2" and s["task_id"]==TASK
    assert s["execution"]=="NONE" and s["real_money"]=="NO-GO"
    q=s["queue"]
    names=s.get("security_names") or {}
    disc=s.get("discovery") or {}
    dm=s.get("discovery_meta") or {}
    exc=s.get("explicit_excluded_reason_counts") or {}
    identity_unknown=sorted(set(s.get("identity_unknown_symbols") or []))
    identity_unknown_detail=s.get("identity_unknown_detail") or {}
    raw_identity_total=int(s.get("raw_identity_total",-1))
    partition_policy=str(s.get("identity_partition_policy") or "")
    proof={
      "queue_unique":len(set(q))==len(q),
      "queue_total_exact":int(s.get("queue_total",-1))==len(q),
      "queue_hash_exact":s.get("queue_hash")==hash_lines(q),
      "security_names_exact":set(names)==set(q),
      "discovery_exact":set(disc)==set(q),
      "full_identity":bool(dm.get("full_identity")),
      "authority_full_identity":valid_full_identity_authority(dm),
      "official_footer_present":bool(s.get("official_footer")),
      "official_footer_asof_exact":official_footer_asof_exact(s.get("official_footer"),s.get("asof_et")),
      "identity_authority_v6":s.get("identity_authority")=="NASDAQTRADER_EXPLICIT_TYPE_FILTER_V6_ASOF_IDENTITY_AND_SPAC_PROOF_AT_MASTER",
      "identity_ruleset_v6":s.get("identity_ruleset")=="V6_ASOF_IDENTITY_AND_SPAC_PROOF_AT_MASTER",
      "exclusion_reasons_policy_exact":set(exc).issubset(ALLOWED_EXCLUSION_REASONS),
      "sec_spac_proof_binding":valid_sec_spac_proof_binding(dm,s.get("asof_et")),
      "asof_identity_proof_binding":valid_asof_identity_proof_binding(dm,s.get("asof_et")),
      "identity_partition_policy_exact":partition_policy=="MASTER_SPAC_OFFICIAL_BLANK_EXCLUDE_V4_EXACT_ASOF_SNAPSHOT_GUARD" and dm.get("identity_partition_policy")==partition_policy,
      "identity_unknown_partition_exact":(
        len(identity_unknown)==len(set(identity_unknown))
        and set(identity_unknown_detail)==set(identity_unknown)
        and not (set(identity_unknown)&set(q))
        and int(dm.get("identity_unknown_count",-1))==len(identity_unknown)
        and dm.get("identity_unknown_hash")==hash_lines(identity_unknown)
        and raw_identity_total==len(q)+len(identity_unknown)
        and int(dm.get("raw_identity_total",-1))==raw_identity_total
        and all((identity_unknown_detail.get(sym) or {}).get("unknown_never_pass") is True for sym in identity_unknown)
      ),
    }
    complete=all(proof.values())
    identity_pass=sorted(q) if complete else []
    effective_unknown=identity_unknown if complete else sorted(set(q)|set(identity_unknown))
    obj={
      "schema":"XRAY_CANONICAL_CURRENT_MASTER_MANIFEST_V1",
      "task_id":TASK,"asof_et":s["asof_et"],
      "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
      "phase":"MASTER_IDENTITY",
      # queue_total is the exact identity-PASS partition consumed by PRICE.
      # raw_identity_total also includes fail-closed identity UNKNOWN symbols.
      "status":("HISTORY_COMPLETE" if complete and not effective_unknown else "PARTIAL_UNKNOWN" if complete else "PARTIAL"),
      "status_semantics":("IDENTITY_COMPLETE" if complete and not effective_unknown else "IDENTITY_PARTITION_EXACT_WITH_UNKNOWN" if complete else "IDENTITY_PARTIAL"),
      "queue_total":len(q),"queue_hash":s["queue_hash"],"queue_unique":len(set(q)),
      "raw_identity_total":raw_identity_total if complete else len(q)+len(effective_unknown),
      "unknown_count":len(effective_unknown),
      "unknown_symbols":effective_unknown,
      "unknown_detail":identity_unknown_detail if complete else {sym:(identity_unknown_detail.get(sym) or {"reason":"IDENTITY_PARTITION_INVALID","unknown_never_pass":True}) for sym in effective_unknown},
      "pending_retry":0,
      "pass_count":len(identity_pass),
      "pass_symbols":identity_pass,
      "pass_hash":hash_lines(identity_pass),
      "counts":{"PASS_IDENTITY":len(identity_pass),"UNKNOWN_IDENTITY":len(effective_unknown)},
      "identity_partition_policy":partition_policy,
      "official_footer":s.get("official_footer"),
      "identity_authority":s.get("identity_authority"),
      "identity_ruleset":s.get("identity_ruleset"),
      "explicit_excluded_count":s.get("explicit_excluded_count"),
      "explicit_excluded_hash":s.get("explicit_excluded_hash"),
      "explicit_excluded_reason_counts":exc,
      "sec_spac_proof":{"path":dm.get("sec_spac_proof_path"),"blob_sha":dm.get("sec_spac_proof_blob_sha"),"count":int(dm.get("sec_spac_proof_count",0) or 0),"symbol_hash":dm.get("sec_spac_proof_hash")},
      "asof_identity_proof":{"path":dm.get("asof_identity_proof_path"),"blob_sha":dm.get("asof_identity_proof_blob_sha"),"counts":dm.get("asof_identity_proof_counts") or {}},
      "history_price_state_diagnostic_only":{
        "source_status":s.get("status"),
        "source_unknown_count":s.get("unknown_count"),
        "source_pending_retry":s.get("pending_retry"),
        "source_counts":s.get("counts") or {},
      },
      "source_state_path":str(INPUT.relative_to(ROOT.parent)).replace("\\","/") if INPUT.is_relative_to(ROOT.parent) else str(INPUT),
      "source_state_blob_sha":blob_sha(INPUT),
      "source_state_hash":s.get("state_hash"),
      "completion_proof":proof,
    }
    OUT.write_text(json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    print(json.dumps({
      "asof":obj["asof_et"],"status":obj["status"],"phase":obj["phase"],
      "queue_total":obj["queue_total"],"identity_unknown":obj["unknown_count"],
      "identity_pass":obj["pass_count"],
      "diagnostic_history_price_unknown":(obj["history_price_state_diagnostic_only"] or {}).get("source_unknown_count")
    },sort_keys=True))

if __name__=="__main__":
    main()
