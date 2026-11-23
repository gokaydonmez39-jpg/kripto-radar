#!/usr/bin/env python3
"""ONLY the existing Kronos V2 monthly research writer may use this transport.

This is NOT a general Sheets writer, a protected-tag lease, an EOD producer,
a trading system or a delivery mechanism. The canonical EOD SheetApi guards
remain unchanged. No write happens without independent, fresh parent GETs
and complete original private scan + score parent identity readback.
"""
from __future__ import annotations

from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import json
import os

import kronos_shadow as k
import private_sheet_writer as writer
import research_epoch_binding as binding

WORKFLOW_REF = (binding.REPO +
    "/.github/workflows/xray-personal-kronos-shadow.yml@refs/heads/main")
ERR = "KRONOS2_RESEARCH_POST_UNVERIFIED"


def gate(ok):
    if not ok:
        raise writer.HandoffBlocked(ERR)


class KronosV2ResearchApi(writer.SheetApi):
    _kronos_v2_writer = True
    """Authenticated GET reuse; POST is restricted to one Kronos monthly tab.

    Never use this class for EOD, candidate, alert, PANEL, score or NEON
    writes. The production original SheetApi remains the unchanged owner.
    """

    def __init__(self, secret, *, parent):
        gate(type(parent) is binding.Parent)
        gate(binding.scheduled_parent(os.environ) == parent)
        super().__init__(secret)
        self._research_parent = parent
        self._research_scope = None

    def arm(self, asof, symbols, scope_sha, policy_sha, scan_id):
        """Called only after v2.private_authority verified original Sheet."""
        import kronos_v2 as v2
        gate(getattr(self, "_authenticated_production_client",False) is True)
        gate(binding.scheduled_parent(os.environ) == self._research_parent)
        gate(os.environ.get("GITHUB_REF") == "refs/heads/main" and
             os.environ.get("GITHUB_WORKFLOW_REF") == WORKFLOW_REF and
             os.environ.get("GITHUB_RUN_ATTEMPT") == "1" and
             os.environ.get("GITHUB_EVENT_NAME") == "workflow_run")
        gate(k.eligible_shadow_asof() == asof)
        gate(type(symbols) is list and len(symbols) == 477 and
             len(set(symbols)) == 477 and
             all(type(s) is str for s in symbols))
        gate(v2.month_sheet(asof) == "KRONOS2_"+asof[:7].replace("-","_"))
        gate(type(scope_sha) is str and len(scope_sha) == 64 and
             type(policy_sha) is str and len(policy_sha) == 64 and
             scan_id == asof)
        self._research_scope=(asof,frozenset(symbols),scope_sha,policy_sha,scan_id)

    def _last_mile(self):
        """No fake parent event, stale Sheet or unverified GitHub EOD can POST."""
        import kronos_v2 as v2
        import preopen_a34 as evidence
        gate(getattr(self, "_authenticated_production_client",False) is True)
        scope=getattr(self,"_research_scope",None)
        gate(type(scope) is tuple and len(scope) == 5)
        asof,symbols,sha,policy,scan_id=scope
        gate(binding.scheduled_parent(os.environ) == self._research_parent)
        gate(k.eligible_shadow_asof() == asof)
        try:
            actual=v2.private_authority(self,asof,parent=self._research_parent)
            gate(frozenset(actual[0])==symbols and
                 actual[1:]==(sha,policy,scan_id))
            run_link=binding.EOD_WEB+str(self._research_parent.run_id)
            gate(evidence.verify_github_natural_eod_source(asof,run_link)
                 == "GITHUB_NATURAL_EOD_SOURCE_VERIFIED")
            gate(evidence.verify_github_eod_six_job_chain(
                asof,run_link,now=datetime.now(timezone.utc))
                 == "GITHUB_NATURAL_EOD_SIX_JOB_VERIFIED")
        except Exception:
            raise writer.HandoffBlocked(ERR) from None
        return scope

    def _allow_payload(self, body, scope):
        import kronos_v2 as v2
        from collections import Counter
        asof,symbols,sha,policy,scan_id=scope
        name=v2.month_sheet(asof)
        gate(type(body) is dict and set(body)=={"requests"} and
             type(body["requests"]) is list and len(body["requests"]) in (1,2))
        meta=super().request(
            "?fields=properties(timeZone),sheets.properties(sheetId,title,gridProperties(rowCount,columnCount))")
        gate(type(meta) is dict and meta.get("properties",{}).get("timeZone")=="Europe/Istanbul")
        ss=[s["properties"] for s in meta.get("sheets",[])
            if type(s) is dict and type(s.get("properties")) is dict]
        matching=[s for s in ss if s.get("title")==name]
        gate(len(matching)<=1)
        all_ids=[s.get("sheetId") for s in ss]
        gate(all(type(x) is int for x in all_ids) and
             len(all_ids)==len(set(all_ids)))
        req=body["requests"]
        if len(req)==2:
            gate(not matching)
            sid=v2.choose_sheet_id(name,set(all_ids))
            expected={"requests":[
                {"addSheet":{"properties":{"sheetId":sid,"title":name,
                    "gridProperties":{"rowCount":2,"columnCount":20,"frozenRowCount":1}}}},
                writer.as_cells([list(k.HEADERS)],sid)]}
            gate(body==expected)
            return
        gate(len(matching)==1 and type(matching[0].get("sheetId")) is int)
        sid=matching[0]["sheetId"]
        item=req[0]
        gate(type(item) is dict and set(item)=={"appendCells"})
        batch=item["appendCells"]
        gate(type(batch) is dict and
             set(batch)=={"sheetId","rows","fields"} and
             batch.get("sheetId")==sid and
             batch.get("fields")=="userEnteredValue")
        raw=batch.get("rows")
        gate(writer._valid_private_string_rows(raw) and
             len(raw)<=v2.WRITE_BATCH_ROWS)
        rows=[]
        for x in raw:
            vals=x["values"]
            gate(len(vals)==20)
            row=[cell["userEnteredValue"]["stringValue"] for cell in vals]
            gate(row[1]==asof and row[2] in symbols and
                 row[11]==sha and row[12]==policy and
                 row[13]==scan_id and row[16]==v2.VERSION_V2 and
                 row[3] in ("1","5","12") and
                 row[0]==f"{asof}|{row[2]}|H{row[3]}" and
                 row[19]==k.canonical_sha(row[:19]) and
                 (row[17] in (v2.MODEL_STATUS_FULL,v2.MODEL_STATUS_CLOSE)
                  or row[17].startswith(v2.QUALITY_PREFIX)))
            if row[17].startswith(v2.QUALITY_PREFIX):
                gate(row[5]==row[6]==row[15]=="")
            rows.append(row)
        gate(len({r[0] for r in rows})==len(rows))
        pairs=Counter((r[1],r[2]) for r in rows)
        gate(all(c==3 for c in pairs.values()))
        gate(all({r[3] for r in rows if r[2]==symbol}=={"1","5","12"}
                 for _,symbol in pairs))
        gate(rows==sorted(rows,key=lambda r:(r[2],int(r[3]))))
        # Reuse the independent *research* ledger validator: the source
        # transport cannot accept arbitrary invented numeric forecasts,
        # model identities, unknown QC states or a partial H1/H5/H12 group.
        try:
            import kronos_oos_audit as oos
            oos.validate_ledger([list(k.HEADERS)]+rows)
        except Exception:
            raise writer.HandoffBlocked(ERR) from None

    def request(self,path,*,method="GET",body=None):
        if method!="POST":
            return super().request(path,method=method,body=body)
        gate(type(path) is str and path==":batchUpdate")
        scope=self._last_mile()
        try:
            self._allow_payload(body,scope)
        except writer.HandoffBlocked:
            raise
        except Exception:
            # An unexpected/malformed metadata or nested batch response is
            # HOLD, never an unredacted Python/provider diagnostic.
            raise writer.HandoffBlocked(ERR) from None
        # One HTTP POST only. Malformed ack, 4xx/5xx, socket reset or timeouts
        # all become a fixed HOLD. v2 performs immutable prefix readback by GET;
        # it NEVER replays a possibly committed batch automatically.
        try:
            req=Request(self.base+path,
                data=json.dumps(body,ensure_ascii=False,allow_nan=False).encode("utf-8"),
                method="POST",headers={
                   "Authorization":"Bearer "+self.token,
                   "Content-Type":"application/json; charset=utf-8"})
            with urlopen(req,timeout=30) as response:
                return json.load(response)
        except (HTTPError,URLError,TimeoutError,OSError,
                ValueError,UnicodeError,TypeError):
            raise writer.HandoffBlocked("KRONOS2_RESEARCH_POST_UNCERTAIN") from None
