"""Source parser quarantine contracts must be accepted by both root audits.

Regression for the exact statuses introduced by PR #132. No market or HTTP IO.
"""
import datetime as dt
import hashlib
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sina_state_hash_guard import seal
from root_history_recovery_microaudit import audit as root_audit
from history_unknown_source_triage import audit as triage_audit


def fixture():
    info={
       "AAA":{"reason":"SINA_SOURCE_SCHEMA_NONRETRYABLE",
              "exception_type":"SyntaxError",
              "retryable_in_same_epoch":False,
              "source_authority":"UNVERIFIED"},
       "BBB":{"reason":"SINA_SOURCE_HTTP_NONRETRYABLE",
              "http_status":403,"retryable_in_same_epoch":False,
              "source_authority":"UNVERIFIED"}}
    q=sorted(info)
    rows={sym:{"status":"UNKNOWN_STATIC","info":d,"attempts":1}
          for sym,d in info.items()}
    state={"schema":"XRAY_NASDAQ_SCREENER_SINA_V2","execution":"NONE",
           "real_money":"NO-GO","unknown_never_pass":True,
           "asof_et":"2026-10-16","status":"HISTORY_PARTIAL",
           "queue":q,"queue_total":len(q),"cursor":len(q),"results":rows,
           "queue_hash":hashlib.sha256("\n".join(q).encode()).hexdigest(),
           "counts":{"UNKNOWN_STATIC":2},"unknown_count":2,"pending_retry":0}
    seal(state)
    root={"schema":"XRAY_ORCHESTRATOR_V1","asof_et":"2026-10-16",
          "execution":"NONE","real_money":"NO-GO","status":"PARTIAL_HISTORY",
          "unknown_count":2,"pending_retry":0,"history_retryable":False}
    return state,root,dt.datetime(2026,10,19,8,35,tzinfo=dt.timezone.utc)


class StaticReasonPipelineContract(unittest.TestCase):
    def test_root_accepts_new_producer_static_reason_codes_as_unknown(self):
        state,root,now=fixture()
        out=root_audit(state,root,now)
        self.assertEqual(out["unknown_count"],2)
        self.assertEqual(out["known_status_counts"]["UNKNOWN_STATIC"],2)
        self.assertEqual(out["independent_history_or_asof_proof_required_count"],2)
        self.assertEqual(out["eligible_single_round_real_provider_retries_now"],0)
        self.assertFalse(out["alpha_authority"])
        self.assertFalse(out["source_proof_full_history_attested"])

    def test_triage_keeps_distinct_actionable_reason_codes(self):
        state,_,_=fixture()
        out=triage_audit(state)
        diagnoses=out["public_per_symbol_source_diagnostics"]
        self.assertEqual(diagnoses["AAA"]["provider_reason_code"],
                         "SINA_SOURCE_SCHEMA_NONRETRYABLE")
        self.assertEqual(diagnoses["AAA"]["operational_class"],
                         "PROVIDER_PARSER_OR_SCHEMA_ERROR")
        self.assertEqual(diagnoses["BBB"]["provider_reason_code"],
                         "SINA_SOURCE_HTTP_NONRETRYABLE")
        self.assertEqual(diagnoses["BBB"]["operational_class"],
                         "PROVIDER_HTTP_DEFINITIVE_NONRETRYABLE")
        self.assertFalse(out["recovery_execution_authorized"])
        self.assertFalse(out["per_symbol_causes_are_independently_verified"])


if __name__=="__main__":
    unittest.main()
