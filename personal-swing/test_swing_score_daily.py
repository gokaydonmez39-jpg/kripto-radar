"""Synthetic-only XRAY 477 swing score V1 regressions, NO IEX API/Sheets."""
import copy
import re
import unittest
from unittest.mock import patch

import exchange_calendars as ec

import private_lifecycle as life
import private_sheet_writer as writer
import swing_score_daily as score

ASOF = "2026-11-04"
SHA = "a" * 64
POLICY = "b" * 64
RUN = "https://github.com/gokaydonmez39-jpg/kripto-radar/actions/runs/41935261378"

def candidate(day, symbol, held):
    return [day + "|" + symbol, day, symbol, "TEKNİK AL ADAYI",
            "100", "90", "120", "AÇIK • %d/15 SEANS" % held,
            "", "", "", "TEST", "SYNTHETIC_ONLY"]

def inputs():
    candidates = [
        list(writer.CANDIDATE_HEADER),
        candidate("2026-11-03", "AAA", 1),
        candidate("2026-11-04", "AAA", 0),
        candidate("2026-11-04", "BBB", 0),
    ]
    scan = [ASOF, writer.RUN_EVENT_LABELS["schedule"], "477", "477", "477",
            "0", "TRUE", "3", RUN,
            "scopeSHA=" + SHA + ";algorithmSHA=" + POLICY +
            ";source_event=schedule;NO_ORDERS"]
    scans = [list(writer.SCAN_HEADER), scan]
    alert = [""] * len(life.ALERT_HEADER)
    alert[0:6] = ["2026-11-04|BBB|2026-11-04|AL_NEW_EPISODE|1",
                  "2026-11-04|BBB", ASOF, "BBB", ASOF, "AL_NEW_EPISODE"]
    alert[17] = "DUPLICATE_ACTIVE_EPISODE_NO_NEW_ALERT"
    return candidates, scans, [list(life.ALERT_HEADER), alert]

def bars(price_shift=0., count=52):
    days=[str(s.date()) for s in ec.get_calendar("XNAS").sessions_in_range(
        "2026-08-01", ASOF)][-count:]
    return [
        {"timestamp": day + "T05:00:00+00:00",
         "open": 49.+i+price_shift, "high": 49.75+i+price_shift,
         "low": 48.75+i+price_shift, "close": 49.5+i+price_shift,
         "volume": 10000+i*25}
        for i,day in enumerate(days)
    ]

class FakeAPI:
    def __init__(self):
        self.candidates, self.scans, self.alerts=inputs()
        self.scored=[list(score.HEADER)]
        self.writes=0
        self.tabid=678912343
    def check_metadata(self):
        return None
    def request(self,path,*,method="GET",body=None):
        if path.startswith("?fields="):
            return {"properties":{"timeZone":"Europe/Istanbul"},
                    "sheets":[{"properties":{"title":score.TAB,
                                             "sheetId":self.tabid}}]}
        if path.startswith("/values/"):
            rows=copy.deepcopy(self.scored)
            return {"values":[row[:max([i+1 for i,v in enumerate(row)
                                          if v != ""] or [0])] for row in rows]}
        if path==":batchUpdate":
            assert method=="POST" and self.writes==0
            self.writes+=1
            requests=body["requests"]
            assert len(requests)==1 and requests[0]["appendCells"]["sheetId"]==self.tabid
            for row in requests[0]["appendCells"]["rows"]:
                self.scored.append([cell["userEnteredValue"]["stringValue"]
                                    for cell in row["values"]])
            return {"replies":[{}]}
        raise AssertionError("Unexpected request")
    def read(self,name,last_col):
        if name==score.TAB: return copy.deepcopy(self.scored)
        if name=="ADAY_GECMISI":return copy.deepcopy(self.candidates)
        if name=="TARAMA_KAYITLARI":return copy.deepcopy(self.scans)
        if name=="UYARI_OLAYLARI":return copy.deepcopy(self.alerts)
        raise AssertionError(name)

class SwingScoreTests(unittest.TestCase):
    def setUp(self):
        self.patches=[
            patch.object(score.runner,"get_scope",return_value=["AAA","BBB"]),
            patch.object(score.runner,"sha_symbols",return_value=SHA),
            patch.object(score.runner,"analysis_fingerprint",return_value=POLICY)
        ]
        for p in self.patches:p.start()
        self.addCleanup(lambda: [p.stop() for p in reversed(self.patches)])
        self.api=FakeAPI()

    def read_batch(self,syms,asof):
        self.assertEqual(asof,ASOF)
        self.assertEqual(syms,["AAA","BBB"])
        return {"AAA":bars(), "BBB":bars(1.)}

    def test_all_open_episodes_ranked_with_duplicate_symbol_counted_once(self):
        rows=score.build(*inputs(),ASOF,self.read_batch)
        self.assertEqual(len(rows),4)
        self.assertEqual(rows[0][4],"SUMMARY")
        self.assertEqual(rows[0][5],"3")
        self.assertEqual(rows[0][6],"3")
        self.assertEqual(rows[0][8],"2")
        self.assertEqual(len({r[2] for r in rows[1:]}),3)
        self.assertEqual([int(r[5]) for r in rows[1:]], [1,2,3])
        aaa=[r for r in rows[1:] if r[3]=="AAA"]
        self.assertEqual(len(aaa),2)
        self.assertEqual(aaa[0][6],aaa[1][6])
        self.assertLessEqual(abs(sum(float(x) for x in aaa[0][7:14])-
                                 float(aaa[0][6])),0.35)
        self.assertTrue(all(0<=float(r[6])<=100 for r in rows[1:]))
        self.assertTrue(all(r[16]=="90.000" and r[17]=="120.000"
                            for r in rows[1:]))
        self.assertTrue(all(re.fullmatch("[0-9a-f]{64}",r[29]) for r in rows))
        self.assertTrue(any("ONCEKI_AL_BASKILANDI" in r[25] for r in rows[1:]))

    def test_missing_symbol_is_hold_not_fabricated(self):
        def missing(syms,asof):
            return {"AAA":bars(),"BBB":[]}
        rows=score.build(*inputs(),ASOF,missing)
        self.assertEqual(rows[0][6],"2")
        self.assertEqual(rows[0][7],"1")
        self.assertEqual(rows[-1][5],"HOLD")
        self.assertEqual(rows[-1][6],"")
        self.assertIn("HOLD_VERI_YETERSIZ",rows[-1][25])

    def test_non_natural_eod_is_rejected_before_provider(self):
        c,s,a=inputs()
        s[1][1]=writer.RUN_EVENT_LABELS["workflow_dispatch"]
        s[1][9]=s[1][9].replace("source_event=schedule",
                                  "source_event=workflow_dispatch")
        def provider_must_not_run(*args):
            raise AssertionError("NON_NATURAL_SOURCE_READ_PROVIDER_FORBIDDEN")
        with self.assertRaisesRegex(writer.HandoffBlocked,
                                    "SWING_SCORE_NON_NATURAL_SOURCE"):
            score.build(c,s,a,ASOF,provider_must_not_run)

    def test_wrong_provenance_is_refused_before_provider(self):
        c,s,a=inputs()
        s[1][9]=s[1][9].replace(SHA,"c"*64)
        def prohibited(syms,asof):
            raise AssertionError("Provider must not be called")
        with self.assertRaisesRegex(writer.HandoffBlocked,"SWING_SCORE_SOURCE_SHA_DRIFT"):
            score.build(c,s,a,ASOF,prohibited)

    def test_broken_final_coverage_fails_closed(self):
        c,s,a=inputs()
        s[1][4]="476"
        with self.assertRaisesRegex(writer.HandoffBlocked,"SWING_SCORE_SCAN_NOT_FINAL_477"):
            score.build(c,s,a,ASOF,self.read_batch)

    def test_score_phase_success_and_guard_failure_are_distinct(self):
        phases=[]
        result=score.synchronize(self.api,ASOF,self.read_batch,on_phase=phases.append)
        self.assertEqual(result["status"],"SWING_SCORE_PRIVATE_READBACK_PASS")
        self.assertEqual(phases,["SHEET_METADATA","SCORE_LEDGER_READ","SOURCE_LEDGER_READ",
            "SOURCE_VALIDATE_AND_SCORE","EXISTING_SCORE_VALIDATE","PREWRITE_REVALIDATE",
            "APPEND_GATE_OR_POST","POST_READBACK"])
        api=FakeAPI()
        phases=[]
        with patch.object(api,"read",side_effect=writer.HandoffBlocked("SHEET_HEADER_DRIFT")):
            with self.assertRaisesRegex(writer.HandoffBlocked,"SHEET_HEADER_DRIFT"):
                score.synchronize(api,ASOF,self.read_batch,on_phase=phases.append)
        self.assertEqual(phases[-1],"SOURCE_LEDGER_READ")
        self.assertEqual(api.writes,0)

    def test_safe_hold_reason_is_exact_allowlist_not_prefix_or_raw_exception(self):
        for raw,want in (("SWING_SCORE_CONCURRENT_MODIFICATION","SWING_SCORE_CONCURRENT_MODIFICATION"),
                         ("SOURCE_LASTMILE_PROVENANCE_UNVERIFIED","SOURCE_LASTMILE_PROVENANCE_UNVERIFIED"),
                         ("SWING_SCORE_PRIVATE_ACCOUNT_12345","UNCLASSIFIED"),
                         ("SWING_SCORE_SOURCE_SHA_DRIFT\nPRIVATE_SECRET","UNCLASSIFIED"),
                         ("https://private.example/secret","UNCLASSIFIED")):
            with self.subTest(raw=raw):
                receipt=score.safe_hold_receipt(writer.HandoffBlocked(raw),"PREWRITE_REVALIDATE")
                self.assertEqual(receipt["reason_code"],want)
                self.assertEqual(receipt["failure_phase"],"PREWRITE_REVALIDATE")
                self.assertEqual(receipt["status"],"SWING_SCORE_HOLD")
                self.assertEqual(receipt["execution"],"NONE")
        self.assertEqual(score.safe_hold_receipt(ValueError("PRIVATE_SECRET"),"POST_READBACK")["reason_code"],"UNCLASSIFIED")
        self.assertEqual(score.safe_hold_receipt(writer.HandoffBlocked("SHEET_HEADER_DRIFT"),"PRIVATE_SECRET")["failure_phase"],"UNCLASSIFIED")

    def test_17_open_episodes_15_unique_symbols_exact_score_batch_transport(self):
        # Same cardinality as the 24-Nov observed ledger, synthetic IDs/bars.
        symbols=["X%02d"%i for i in range(15)]
        candidates=[list(writer.CANDIDATE_HEADER)]+[candidate(ASOF,s,0) for s in symbols]
        candidates.extend([candidate("2026-11-03",s,1) for s in symbols[:2]])
        _,scans,alerts=inputs()
        scans[1][7]="15"
        alerts=[list(life.ALERT_HEADER)]
        rows=score.build(candidates,scans,alerts,ASOF,
                        lambda syms,asof:{s:bars(i*.01) for i,s in enumerate(syms)})
        self.assertEqual(len(rows),18)
        self.assertEqual(rows[0][5],"17")
        self.assertEqual(rows[0][8],"15")
        self.assertEqual(len({r[2] for r in rows[1:]}),17)
        scope={"scan":1,"candidate":2,"alerts":3,"panel":4,"score":5}
        payload={"requests":[writer.as_cells(rows,5)]}
        self.assertTrue(writer._valid_private_batch_post(payload))
        self.assertTrue(writer._valid_private_batch_targets(payload,scope))

    def _seed_prior_summary_and_pending_alert(self):
        prior = [""] * len(score.HEADER)
        prior[:2] = ["2026-11-03|SUMMARY", "2026-11-03"]
        prior[4] = "SUMMARY"
        prior[27] = score.READY
        prior[29:33] = ["c" * 64, SHA, POLICY, score.VERSION]
        self.api.scored.append(prior)
        self.api.alerts[1][17:19] = [life.EVENT_PENDING, ""]
        return prior

    def test_one_stable_delivery_only_snapshot_refresh_keeps_single_post(self):
        prior = self._seed_prior_summary_and_pending_alert()
        reads = {"score": 0, "alerts": 0}
        old_request, old_read = self.api.request, self.api.read
        def request(path, **kw):
            if path.startswith("/values/"):
                reads["score"] += 1
                if reads["score"] == 2:
                    prior[27:29] = [score.REQUESTED, "2026-11-04 08:57 TRT"]
            return old_request(path, **kw)
        def read(name, last_col):
            if name == "UYARI_OLAYLARI":
                reads["alerts"] += 1
                if reads["alerts"] == 2:
                    self.api.alerts[1][17:19] = [
                        "ALERT_REQUESTED_NOT_DEVICE_ACK", "2026-11-04 08:57 TRT"]
            return old_read(name, last_col)
        with patch.object(self.api, "request", side_effect=request), \
             patch.object(self.api, "read", side_effect=read), \
             patch.object(self, "read_batch", wraps=self.read_batch) as provider:
            result = score.synchronize(self.api, ASOF, self.read_batch)
        self.assertEqual(result["status"], "SWING_SCORE_PRIVATE_READBACK_PASS")
        self.assertEqual(self.api.writes, 1)
        self.assertEqual(provider.call_count, 1)
        self.assertEqual(reads, {"score": 4, "alerts": 3})
        self.assertEqual(prior[27], score.REQUESTED)

    def test_delivery_snapshot_drift_again_blocks_without_post(self):
        self._seed_prior_summary_and_pending_alert()
        count = 0
        old_read = self.api.read
        def read(name, last_col):
            nonlocal count
            if name == "UYARI_OLAYLARI":
                count += 1
                if count == 2:
                    self.api.alerts[1][17:19] = [
                        "ALERT_REQUESTED_NOT_DEVICE_ACK", "2026-11-04 08:57 TRT"]
                if count == 3:
                    self.api.alerts[1][19] = "CHANGED_IMMUTABLE_NOTE"
            return old_read(name, last_col)
        with patch.object(self.api, "read", side_effect=read):
            with self.assertRaisesRegex(writer.HandoffBlocked,
                                        "SWING_SCORE_CONCURRENT_MODIFICATION"):
                score.synchronize(self.api, ASOF, self.read_batch)
        self.assertEqual(self.api.writes, 0)

    def test_post_readback_allows_prior_summary_request_but_not_digest_change(self):
        for corrupt in (False, True):
            with self.subTest(corrupt=corrupt):
                self.api = FakeAPI()
                prior = self._seed_prior_summary_and_pending_alert()
                count = 0
                old_request = self.api.request
                def request(path, **kw):
                    nonlocal count
                    if path.startswith("/values/"):
                        count += 1
                        if count == 3:
                            prior[27:29] = [score.REQUESTED, "2026-11-04 08:57 TRT"]
                            if corrupt:
                                prior[29] = "d" * 64
                    return old_request(path, **kw)
                with patch.object(self.api, "request", side_effect=request):
                    if corrupt:
                        with self.assertRaisesRegex(writer.HandoffBlocked,
                                                    "SWING_SCORE_READBACK_MISMATCH"):
                            score.synchronize(self.api, ASOF, self.read_batch)
                    else:
                        result = score.synchronize(self.api, ASOF, self.read_batch)
                        self.assertEqual(result["status"], "SWING_SCORE_PRIVATE_READBACK_PASS")
                self.assertEqual(self.api.writes, 1)

    def test_delivery_only_revalidation_rejects_every_other_transition(self):
        prior = self._seed_prior_summary_and_pending_alert()
        before = copy.deepcopy(self.api.alerts)
        good = copy.deepcopy(before)
        good[1][17:19] = ["ALERT_REQUESTED_NOT_DEVICE_ACK", "2026-11-04 08:57 TRT"]
        self.assertTrue(score._delivery_only_progress(before, good, score_ledger=False))
        for col, value in ((0, "OTHER_ID"), (5, "STOP_TOUCHED"),
                           (17, "DUPLICATE_ACTIVE_EPISODE_NO_NEW_ALERT"),
                           (17, "DEVICE_ACK"), (18, "2026-11-03 08:57 TRT"),
                           (18, "2026-11-04 25:00 TRT"), (19, "OTHER_NOTE")):
            with self.subTest(col=col, value=value):
                other = copy.deepcopy(good)
                other[1][col] = value
                self.assertFalse(score._delivery_only_progress(before, other,
                                                                score_ledger=False))
        self.assertFalse(score._delivery_only_progress(good, before, score_ledger=False))
        self.assertFalse(score._delivery_only_progress(before, good + [good[1]],
                                                        score_ledger=False))
        old_score = [list(score.HEADER), prior]
        new_score = copy.deepcopy(old_score)
        new_score[1][27:29] = [score.REQUESTED, "2026-11-04 08:57 TRT"]
        self.assertTrue(score._delivery_only_progress(old_score, new_score, score_ledger=True))
        new_score[1][29] = "OTHER_DIGEST"
        self.assertFalse(score._delivery_only_progress(old_score, new_score, score_ledger=True))

    def test_no_duplicate_daily_write_and_request_preserved(self):
        original=copy.deepcopy(self.api.candidates)
        out=score.synchronize(self.api,ASOF,self.read_batch)
        self.assertEqual(out["status"],"SWING_SCORE_PRIVATE_READBACK_PASS")
        self.assertEqual(self.api.writes,1)
        self.assertEqual(self.api.candidates,original)
        self.api.scored[1][27]=score.REQUESTED
        self.api.scored[1][28]="2026-11-05 09:57 TRT"
        result=score.synchronize(self.api,ASOF,self.read_batch)
        self.assertEqual(result["status"],"SWING_SCORE_IDEMPOTENT_READBACK_PASS")
        self.assertEqual(self.api.writes,1)
        self.assertEqual(self.api.scored[1][27],score.REQUESTED)

    def test_replay_detects_modified_stop_level(self):
        score.synchronize(self.api,ASOF,self.read_batch)
        self.api.scored[2][16]="0.001"
        with self.assertRaisesRegex(writer.HandoffBlocked,"SWING_SCORE_EXISTING_DAY_CONTENT_DRIFT"):
            score.synchronize(self.api,ASOF,self.read_batch)
        self.assertEqual(self.api.writes,1)

    def test_missing_episode_bar_fails_closed_or_marks_hold(self):
        def bad(syms,asof):
            x=bars()
            x[-1]["timestamp"]="2026-11-03T05:00:00+00:00"
            return {"AAA":x,"BBB":bars(1.)}
        with self.assertRaises((ValueError,writer.HandoffBlocked)):
            score.build(*inputs(),ASOF,bad)

    def test_score_read_uses_open_ended_range_to_avoid_hidden_old_asof(self):
        from urllib.parse import unquote
        seen=[]
        original=self.api.request
        def proxy(path, **kw):
            seen.append(path)
            return original(path, **kw)
        with patch.object(self.api, "request", side_effect=proxy):
            self.assertEqual(len(score.score_read(self.api)),1)
        paths=[unquote(p) for p in seen if p.startswith("/values/")]
        self.assertEqual(len(paths),1)
        self.assertIn("'SWING_SKOR_GUNLUK'!A1:AI", paths[0])
        self.assertNotIn("AI50000", paths[0])

    def test_score_read_at_exact_limit_passes_and_above_limit_blocks(self):
        score.synchronize(self.api,ASOF,self.read_batch)
        with patch.object(score, "MAX_ROWS", len(self.api.scored)):
            self.assertEqual(len(score.score_read(self.api)),len(self.api.scored))
        with patch.object(score, "MAX_ROWS", len(self.api.scored)-1):
            with self.assertRaisesRegex(writer.HandoffBlocked,
                                        "SWING_SCORE_READ_CAPACITY_REACHED"):
                score.score_read(self.api)

    def test_same_day_idempotent_replay_allowed_when_no_new_append_headroom(self):
        score.synchronize(self.api,ASOF,self.read_batch)
        self.assertEqual(self.api.writes,1)
        with patch.object(score, "MAX_ROWS", 6):
            # Four existing rows, four re-created rows would exceed six if
            # the new-ASOF capacity gate ran before immutable replay check.
            result=score.synchronize(self.api,ASOF,self.read_batch)
        self.assertEqual(result["status"],"SWING_SCORE_IDEMPOTENT_READBACK_PASS")
        self.assertEqual(self.api.writes,1)

    def test_score_ledger_rejects_malformed_history_before_provider_or_post(self):
        def prohibited(*args):
            raise AssertionError("Unexpected market read")
        for mutation, reason in (
            ("fake_ack", "DELIVERY"),
            ("bad_timestamp", "DELIVERY"),
            ("overwide", "ROW_SHAPE"),
            ("interior_blank", "ROW_SHAPE"),
            ("bad_pin", "PIN"),
            ("wrong_id", "IDENTITY"),
            ("duplicate", "IDENTITY"),
            ("episode_delivery", "DELIVERY"),
        ):
            with self.subTest(mutation=mutation):
                self.api = FakeAPI()
                self.api.scored += score.build(*inputs(), ASOF, self.read_batch)
                row = self.api.scored[1]
                if mutation == "fake_ack":
                    row[27] = "DEVICE_ACK"
                elif mutation == "bad_timestamp":
                    row[27:29] = [score.REQUESTED, "2026-11-04 25:00 TRT"]
                elif mutation == "overwide":
                    row.append("EXTRA")
                elif mutation == "interior_blank":
                    self.api.scored.insert(2, [""])
                elif mutation == "bad_pin":
                    row[29] = "NOT_SHA"
                elif mutation == "wrong_id":
                    row[0] = ASOF + "|OTHER"
                elif mutation == "duplicate":
                    self.api.scored.append(copy.deepcopy(row))
                elif mutation == "episode_delivery":
                    self.api.scored[2][27] = score.REQUESTED
                with self.assertRaisesRegex(writer.HandoffBlocked,
                                            "SWING_SCORE_LEDGER_" + reason):
                    score.synchronize(self.api, ASOF, prohibited)
                self.assertEqual(self.api.writes, 0)

    def test_score_ledger_guard_reasons_are_redacted_static_codes(self):
        for suffix in ("ROW_SHAPE", "IDENTITY", "PIN", "DELIVERY"):
            code = "SWING_SCORE_LEDGER_" + suffix
            receipt = score.safe_hold_receipt(writer.HandoffBlocked(code),
                                              "SCORE_LEDGER_READ")
            self.assertEqual(receipt["reason_code"], code)
            self.assertEqual(receipt["execution"], "NONE")
            self.assertEqual(receipt["failure_phase"], "SCORE_LEDGER_READ")

    def test_new_asof_append_over_capacity_blocks_before_write(self):
        with patch.object(score, "MAX_ROWS", 4):
            with self.assertRaisesRegex(writer.HandoffBlocked,
                                        "SWING_SCORE_CAPACITY_REACHED"):
                score.synchronize(self.api,ASOF,self.read_batch)
        self.assertEqual(self.api.writes,0)


class DailyScoreWorkflowAcceptanceTests(unittest.TestCase):
    """Pure offline proof: score failure cannot masquerade as a passing EOD."""
    @staticmethod
    def workflow():
        from pathlib import Path
        return (Path(__file__).resolve().parent.parent /
                ".github/workflows/xray-personal-477-eod.yml").read_text(
                    encoding="utf-8")

    @staticmethod
    def job(text, name):
        import re
        marker = re.search(r"(?m)^  " + re.escape(name) + r":\s*$", text)
        if marker is None:
            raise AssertionError("Missing mandatory score acceptance job " + name)
        rest = text[marker.end():]
        end = re.search(r"(?m)^  [A-Za-z][A-Za-z0-9_-]*:\s*$", rest)
        return rest[:end.start()] if end else rest

    @staticmethod
    def step(job, name):
        marker = "      - name: " + name + "\n"
        if job.count(marker) != 1:
            raise AssertionError("Missing or duplicate workflow step " + name)
        rest = job.split(marker, 1)[1]
        return rest.split("\n      - name: ", 1)[0]

    def test_producer_exports_real_outcome_before_continue_on_error(self):
        followups = self.job(self.workflow(), "private-episode-followups")
        self.assertIn("swing_score_outcome:", followups)
        self.assertIn("steps.daily_swing_score.outcome", followups)
        self.assertNotIn("steps.daily_swing_score.conclusion", followups)
        self.assertIn("id: daily_swing_score", followups)
        self.assertIn("continue-on-error: true", followups)
        self.assertIn("python swing_score_daily.py", followups)

    def test_guardian_independent_score_receipt_gate_is_mandatory(self):
        gate = self.job(self.workflow(), "daily-private-score-acceptance")
        self.assertIn("needs: [guardian-acceptance, private-episode-followups]",gate)
        self.assertIn("needs.guardian-acceptance.result == 'success'", gate)
        self.assertIn("github.event_name == 'schedule'", gate)
        self.assertNotIn("workflow_dispatch", gate)
        self.assertNotIn("github.event_name != 'pull_request'", gate)
        self.assertIn("needs.private-episode-followups.outputs.swing_score_outcome",gate)
        self.assertIn('[[ "$SCORE_OUTCOME" == "success" ]]',gate)
        self.assertIn("exit 3",gate)
        header = gate.split("    steps:", 1)[0]
        hard = self.step(gate, "Gate raw score outcome after Guardian (fail closed)")
        self.assertNotIn("continue-on-error", header)
        self.assertNotIn("continue-on-error", hard)
        self.assertNotIn("method: POST",gate)

    def test_required_summary_note_is_schedule_only_after_the_mandatory_gate(self):
        """A missing B note makes the sixth EOD job RED, not false-GREEN."""
        job = self.job(self.workflow(), "daily-private-score-acceptance")
        hard = "Gate raw score outcome after Guardian (fail closed)"
        names = ("Load NASDAQ source evidence bridge (schedule only)",
                 "Prepare private Sheet proof bridge dependencies (schedule only)",
                 "Attach and verify current B evidence note (schedule only)",
                 "Publish redacted B evidence acceptance")
        self.assertEqual(re.findall(r"(?m)^      - name: (.*)$",job),
                         [hard,*names])
        header=job.split("    steps:",1)[0]
        self.assertIn("timeout-minutes: 8",header)
        for index,name in enumerate(names[:3]):
            step=self.step(job,name)
            for predicate in ("success()", "github.event_name == 'schedule'",
                              "github.ref == 'refs/heads/main'",
                              "github.run_attempt == 1"):
                self.assertIn(predicate,step)
            self.assertNotIn("continue-on-error: true",step)
            if index<2:
                self.assertNotIn("XRAY_PRIVATE_SHEET_SERVICE_ACCOUNT_JSON",step)
        prepare,publish=(self.step(job,name) for name in names[1:3])
        self.assertIn("steps.source-note-checkout.outcome == 'success'",prepare)
        self.assertIn("steps.source-note-deps.outcome == 'success'",publish)
        self.assertIn("id: source-note-attach",publish)
        self.assertIn("publish_b_source_note.py",publish)
        result=self.step(job,names[3])
        self.assertIn("always()",result)
        self.assertIn("steps.source-note-attach.outcome",result)
        self.assertIn("XRAY_B_SOURCE_NOTE=PASS_READBACK_NOT_DEVICE_ACK",result)
        self.assertIn("XRAY_B_SOURCE_NOTE=HOLD_NO_READBACK",result)

    def test_no_second_provider_score_run_or_new_schedule(self):
        content = self.workflow()
        self.assertEqual(content.count("python swing_score_daily.py"), 1)
        self.assertEqual(content.count("cron:"), 1)
        self.assertIn("python -m unittest -q test_swing_score_daily", content)
        self.assertIn("python -O -m unittest -q test_swing_score_daily", content)
        self.assertIn("guardian-acceptance:", content)

    def test_receipt_predicate_rejects_failure_skipped_and_unknown(self):
        # The exact accepted outcome is 'success', not a falsy fallback or
        # continue-on-error post-processed conclusion.
        import os
        import subprocess
        statement='[[ "$SCORE_OUTCOME" == "success" ]]'
        for value, valid in (("success", True),("failure", False),
                             ("skipped", False),("", False)):
            env = dict(os.environ, SCORE_OUTCOME=value)
            result = subprocess.run(["bash","-c",statement], env=env,
                                    capture_output=True, check=False)
            self.assertEqual(result.returncode == 0, valid)



class ZeroSessionReceiptFailClosedTests(unittest.TestCase):
    """A successful process exit is not proof of any completed ASOF or score."""
    def test_pre_session_writes_explicit_no_completed_session_not_readback(self):
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            filepath=folder+"/output"
            with patch.dict(os.environ, {"GITHUB_OUTPUT":filepath}):
                with patch.object(score.daily_job,"current_completed_session",return_value=None):
                    self.assertEqual(score.main([]),0)
            result=open(filepath,encoding="utf-8").read()
            self.assertIn("score_status=SWING_SCORE_NO_COMPLETED_SESSION",result)
            self.assertIn("score_asof_et=",result)
            self.assertNotIn("score_status=SWING_SCORE_PRIVATE_READBACK_PASS",result)

    def test_private_readback_is_attested_with_exact_asof(self):
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            filepath=folder+"/output"
            with patch.dict(os.environ, {"GITHUB_OUTPUT":filepath}):
                score.publish_action_receipt(
                    {"status":"SWING_SCORE_PRIVATE_READBACK_PASS",
                     "asof_et":"2026-11-06"})
            result=open(filepath,encoding="utf-8").read()
            self.assertIn("score_status=SWING_SCORE_PRIVATE_READBACK_PASS",result)
            self.assertIn("score_asof_et=2026-11-06",result)

    def test_unknown_or_inconsistent_receipt_is_never_accepted(self):
        import os
        import tempfile
        cases=[
            {"status":"PRIVATE_ROW_AND_TOKEN","asof_et":"2026-11-06"},
            {"status":"SWING_SCORE_PRIVATE_READBACK_PASS","asof_et":""},
            {"status":"SWING_SCORE_PRIVATE_READBACK_PASS","asof_et":"2026-11-05\nEVIL=YES"},
            {"status":"SWING_SCORE_NO_COMPLETED_SESSION","asof_et":"2026-11-06"},
        ]
        with tempfile.TemporaryDirectory() as folder:
            filepath=folder+"/output"
            with patch.dict(os.environ, {"GITHUB_OUTPUT":filepath}):
                for result in cases:
                    with self.assertRaises((ValueError,writer.HandoffBlocked)):
                        score.publish_action_receipt(result)
            self.assertFalse(os.path.exists(filepath))

    def test_mandatory_gate_checks_actual_receipt_not_just_exit_code(self):
        from pathlib import Path
        yaml=(Path(__file__).resolve().parent.parent /
              ".github/workflows/xray-personal-477-eod.yml").read_text("utf-8")
        self.assertIn("steps.daily_swing_score.outputs.score_status",yaml)
        self.assertIn("needs.private-episode-followups.outputs.swing_score_status",yaml)
        self.assertIn("needs.private-episode-followups.outputs.swing_score_asof",yaml)
        self.assertIn("SWING_SCORE_NO_COMPLETED_SESSION",yaml)
        self.assertIn("SWING_SCORE_PRIVATE_READBACK_PASS",yaml)
        self.assertIn("SWING_SCORE_IDEMPOTENT_READBACK_PASS",yaml)
        self.assertIn("NOT_DUE_PRE_SESSION_NO_DAILY_ACCEPTANCE",yaml)



    def test_actual_workflow_bash_gate_truth_table(self):
        import os
        import subprocess
        import textwrap
        from pathlib import Path
        yaml=(Path(__file__).resolve().parent.parent /
              ".github/workflows/xray-personal-477-eod.yml").read_text("utf-8")
        section=DailyScoreWorkflowAcceptanceTests.job(
            yaml,"daily-private-score-acceptance")
        hard = DailyScoreWorkflowAcceptanceTests.step(
            section,"Gate raw score outcome after Guardian (fail closed)")
        self.assertEqual(hard.count("        run: |\n"),1)
        script=textwrap.dedent(hard.split("        run: |\n",1)[1])
        cases=[
            ("push","success","SWING_SCORE_NO_COMPLETED_SESSION","",0,
             "NOT_DUE_PRE_SESSION_NO_DAILY_ACCEPTANCE"),
            ("schedule","success","SWING_SCORE_NO_COMPLETED_SESSION","",3,
             "HOLD_NO_ELIGIBLE_SCHEDULE_SESSION"),
            ("workflow_dispatch","success","SWING_SCORE_NO_COMPLETED_SESSION","",3,
             "HOLD_NO_ELIGIBLE_SCHEDULE_SESSION"),
            ("schedule","success","SWING_SCORE_PRIVATE_READBACK_PASS","2026-11-06",0,
             "PRIVATE_READBACK_PASS_ASOF_2026-11-06"),
            ("schedule","success","SWING_SCORE_IDEMPOTENT_READBACK_PASS","2026-11-06",0,
             "PRIVATE_READBACK_PASS_ASOF_2026-11-06"),
            ("schedule","failure","SWING_SCORE_PRIVATE_READBACK_PASS","2026-11-06",3,
             "HOLD_STEP_FAILURE"),
            ("schedule","success","SYNTHETIC_UNKNOWN_STATUS","2026-11-06",3,
             "HOLD_NO_VALID_READBACK_RECEIPT"),
            ("schedule","success","SWING_SCORE_PRIVATE_READBACK_PASS","",3,
             "HOLD_INVALID_RECEIPT_ASOF"),
            ("push","success","SWING_SCORE_NO_COMPLETED_SESSION","2026-11-06",3,
             "HOLD_NO_ELIGIBLE_SCHEDULE_SESSION"),
        ]
        for event,outcome,status,asof,code,marker in cases:
            env=dict(os.environ,SCORE_OUTCOME=outcome,SCORE_STATUS=status,
                     SCORE_ASOF=asof,EVENT_KIND=event)
            result=subprocess.run(["bash","-c",script],env=env,text=True,
                                  capture_output=True,check=False)
            with self.subTest(event=event,outcome=outcome,status=status,asof=asof):
                self.assertEqual(result.returncode,code)
                self.assertIn(marker,result.stdout+result.stderr)



class ScoreEntrypointNaturalEODSourceTests(unittest.TestCase):
    """No manually sourced / stale score Sheets access, even with credentials."""

    def env(self,event="schedule"):
        return {
            "GITHUB_EVENT_NAME":event,"GITHUB_REPOSITORY":writer.EXPECTED_EOD_REPOSITORY,
            "GITHUB_REF":"refs/heads/main","GITHUB_RUN_ATTEMPT":"1",
            "GITHUB_RUN_ID":"999001","GITHUB_SHA":"a"*40,
            "GITHUB_WORKFLOW_REF":writer.EXPECTED_EOD_WORKFLOW_REF,
            "XRAY_PRIVATE_SHEET_SERVICE_ACCOUNT_JSON":"OFFLINE_SYNTHETIC",
        }

    def test_non_natural_score_run_denied_before_private_client(self):
        import io,contextlib,os,json
        for event in ("workflow_dispatch","push"):
            with self.subTest(event=event):
                with patch.dict(os.environ,self.env(event),clear=True):
                    with patch.object(score.daily_job,"current_completed_session",
                                      return_value=ASOF):
                        with patch.object(score.writer,"SheetApi",
                            side_effect=AssertionError("SCORE_GOOGLE_CLIENT_MUST_NOT_START")
                        ) as client,contextlib.redirect_stdout(io.StringIO()) as output:
                            rc=score.main(["--asof",ASOF])
                self.assertEqual(rc,3)
                self.assertEqual(json.loads(output.getvalue())["status"],"SWING_SCORE_HOLD")
                client.assert_not_called()

    def test_stale_cli_asof_denied_before_private_client(self):
        import io,contextlib,os,json
        with patch.dict(os.environ,self.env(),clear=True):
            with patch.object(score.daily_job,"current_completed_session",
                              return_value="2026-11-05"):
                with patch.object(score.writer,"SheetApi",
                      side_effect=AssertionError("HISTORICAL_SCORE_GOOGLE_CLIENT_STARTED")
                ) as client,contextlib.redirect_stdout(io.StringIO()) as output:
                    rc=score.main(["--asof",ASOF])
        self.assertEqual(rc,3)
        self.assertEqual(json.loads(output.getvalue())["status"],"SWING_SCORE_HOLD")
        client.assert_not_called()

    def test_current_natural_score_can_reach_mock_client(self):
        import io,contextlib,os,json
        mock_result={"status":"SWING_SCORE_IDEMPOTENT_READBACK_PASS","asof_et":ASOF,
                     "active_episodes":2,"scoreable":2,"new_rows":0,"execution":"NONE"}
        with patch.dict(os.environ,self.env(),clear=True):
            with patch.object(score.daily_job,"current_completed_session",
                              return_value=ASOF):
                with patch.object(score.writer,"SheetApi",return_value=self) as client:
                    with patch.object(score,"synchronize",return_value=mock_result) as sync:
                        with contextlib.redirect_stdout(io.StringIO()) as output:
                            rc=score.main(["--asof",ASOF])
        self.assertEqual(rc,0)
        client.assert_called_once_with("OFFLINE_SYNTHETIC")
        sync.assert_called_once()
        self.assertEqual(json.loads(output.getvalue())["status"],
                         "SWING_SCORE_IDEMPOTENT_READBACK_PASS")


if __name__=="__main__":
    unittest.main()
