"""Legacy Sina exhaustion must not retry deterministic parser or 4xx faults.

No vendor calls, OHLCV, trading or production artifact writes.
"""
import datetime as dt
import hashlib
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sina_transport_rescue import choose
from root_history_recovery_microaudit import audit
from sina_state_hash_guard import seal


def fixture():
    now=dt.datetime(2026,10,19,8,30,tzinfo=dt.timezone.utc)
    errors={
        "A_SYNTAX":"SyntaxError:invalid syntax (<string>, line 1)",
        "B_INDEX":"IndexError:list index out of range",
        "C_KEY":"KeyError:'date'",
        "D_JSON":"JSONDecodeError:bad payload",
        "E_403":"HTTPError:HTTP Error 403: Forbidden",
        "F_429":"HTTPError:429",
        "G_TIMEOUT":"TimeoutError:timed out",
        "H_CONN":"ConnectionError:remote reset",
    }
    symbols=sorted(errors)
    rows={s:{"status":"UNKNOWN_RETRY_EXHAUSTED","info":reason,
             "attempts":5,"transport_rescue_round":0,
             "updated_at_utc":"2026-10-18T22:00:00+00:00"}
          for s,reason in errors.items()}
    state={
       "schema":"XRAY_NASDAQ_SCREENER_SINA_V2","execution":"NONE",
       "real_money":"NO-GO","unknown_never_pass":True,
       "asof_et":"2026-10-16","status":"HISTORY_PARTIAL",
       "queue":symbols,"queue_total":len(symbols),"cursor":len(symbols),
       "results":rows,
       "queue_hash":hashlib.sha256("\n".join(symbols).encode()).hexdigest(),
       "counts":{"UNKNOWN_RETRY_EXHAUSTED":len(symbols)},
       "unknown_count":len(symbols),"pending_retry":0,
    }
    seal(state)
    root={"schema":"XRAY_ORCHESTRATOR_V1","asof_et":"2026-10-16",
          "execution":"NONE","real_money":"NO-GO","status":"PARTIAL_HISTORY",
          "unknown_count":len(symbols),"pending_retry":0,"history_retryable":False}
    return state,root,now


class SinaLegacyRescueTests(unittest.TestCase):
    def test_only_true_transports_can_be_retried(self):
        state,root,now=fixture()
        self.assertEqual(choose(state,now),["F_429","G_TIMEOUT","H_CONN"])

    def test_root_causal_categories_match_rescue(self):
        state,root,now=fixture()
        report=audit(state,root,now)
        self.assertEqual(report["source_transport_exception_unknown_count"],3)
        self.assertEqual(report["source_other_exception_unknown_count"],5)
        self.assertEqual(report["independent_history_or_asof_proof_required_count"],5)
        self.assertEqual(report["eligible_single_round_real_provider_retries_now"],3)
        self.assertEqual(report["unknown_count"],8)
        self.assertFalse(report["alpha_authority"])
        self.assertFalse(report["source_proof_full_history_attested"])


if __name__=="__main__":
    unittest.main()
