#!/usr/bin/env python3
"""Current-epoch SEC accession recheck contract and fake-network regression."""
import copy
import os
import sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import sec_current_accession_seven_recheck_shadow as module

def fixture():
    s=sorted({*module.SCOPE,*("Q%04d"%i for i in range(507))})
    assert len(s)==514
    price={"asof_et":"2026-10-09","pass_symbols":s,"pass_count":514,
           "pass_hash":module.hash_lines(s),"execution":"NONE",
           "real_money":"NO-GO","unknown_never_pass":True}
    master={"asof_et":"2026-10-09","pass_symbols":s,"execution":"NONE",
            "real_money":"NO-GO","unknown_never_pass":True}
    return price,master

def test_contract():
    p,m=fixture()
    good=module.scope_contract(p,m,module.PRICE_SHA,module.MASTER_SHA)
    assert good["price_pass_count"]==514 and len(good["seven_scope"])==7
    def denied(p,m,ps,ms):
        try:module.scope_contract(p,m,ps,ms)
        except ValueError:return
        raise AssertionError("STALE_OR_WRONG_SCOPE_ADMITTED")
    denied(p,m,"a"*40,module.MASTER_SHA)
    denied(p,m,module.PRICE_SHA,"b"*40)
    bad=copy.deepcopy(p);bad["asof_et"]="2026-10-08"
    denied(bad,m,module.PRICE_SHA,module.MASTER_SHA)
    bad=copy.deepcopy(m);bad["asof_et"]="2026-10-08"
    denied(p,bad,module.PRICE_SHA,module.MASTER_SHA)
    bad=copy.deepcopy(p);bad["pass_symbols"][0]=bad["pass_symbols"][1]
    denied(bad,m,module.PRICE_SHA,module.MASTER_SHA)
    bad=copy.deepcopy(p);bad["pass_symbols"].remove("CHTR")
    denied(bad,m,module.PRICE_SHA,module.MASTER_SHA)
    bad=copy.deepcopy(m);bad["pass_symbols"].remove("CHTR")
    denied(p,bad,module.PRICE_SHA,module.MASTER_SHA)
    bad=copy.deepcopy(p);bad["execution"]="BUY"
    denied(bad,m,module.PRICE_SHA,module.MASTER_SHA)
    bad=copy.deepcopy(p);bad["real_money"]="GO"
    denied(bad,m,module.PRICE_SHA,module.MASTER_SHA)
    bad=copy.deepcopy(p);bad["unknown_never_pass"]=False
    denied(bad,m,module.PRICE_SHA,module.MASTER_SHA)
    print("XRAY_SEC_CURRENT_SOURCE_SHA_EPOCH_AND_SCOPE=PASS_TEN_NEGATIVES")

def test_network_mock():
    p,m=fixture()
    g=module.scope_contract(p,m,module.PRICE_SHA,module.MASTER_SHA)
    ids={s:1000+i for i,s in enumerate(module.SCOPE)}
    called=[]
    def dummy_fetch(url,ua):
        called.append(url)
        if url==module.SEC_MAP:
            return {"fields":["ticker","cik","exchange"],"data":[[s,n,"Nasdaq"] for s,n in ids.items()]}
        for sym,idx in ids.items():
            cik=f"{idx:010d}"
            accession=cik+"-26-000001"
            if url.endswith("companyfacts/CIK"+cik+".json"):
                return {"cik":idx,"facts":{"dei":{"EntityCommonStockSharesOutstanding":{
                    "units":{"shares":[{"val":1000+idx,"end":"2026-09-30","filed":"2026-10-06",
                                      "form":"10-Q","accn":accession}]}}}}}
            if url.endswith("submissions/CIK"+cik+".json"):
                recent={"accessionNumber":[accession],"form":["10-Q"],
                        "filingDate":["2026-10-06"],"acceptanceDateTime":["2026-10-06T12:00:00-04:00"]}
                if sym=="CHTR":
                    recent={k:[] for k in recent}
                return {"cik":idx,"filings":{"recent":recent,
                        "files":[{"name":"CIK"+cik+"-submissions-001.json",
                                  "filingFrom":"2026-01-01","filingTo":"2026-10-09"}]}}
            if url.endswith("submissions/CIK"+cik+"-submissions-001.json"):
                if sym!="CHTR":raise AssertionError("UNNEEDED_ARCHIVE_READ")
                return {"accessionNumber":[accession],"form":["10-Q"],
                        "filingDate":["2026-10-06"],"acceptanceDateTime":["2026-10-06T12:00:00-04:00"]}
        raise AssertionError("UNAUTHORIZED_ENDPOINT:"+url)
    with patch.object(module,"load_source",return_value=g),patch.dict(os.environ,{"XRAY_SEC_USER_AGENT":"XRAY QA (qa@sample.org)"}):
        result=module.recheck(fetch=dummy_fetch,sleep=lambda _:None)
    assert result["status"]=="CURRENT_SEVEN_OFFICIAL_RECHECK_COMPLETED_SHADOW"
    assert result["price_blob_sha"]==module.PRICE_SHA
    assert result["source"] if False else True
    assert result["reason_counts"]=={
        "SHADOW_CURRENT_ARCHIVE_SHARES_VINTAGE_ONLY":1,
        "SHADOW_CURRENT_RECENT_SHARES_VINTAGE_ONLY":6}
    assert len(result["symbol_statuses"])==7
    assert result["primary_mc_count"]==result["history_pass_count"]==0
    assert result["market_cap_derived"] is False and result["raw_shares_persisted"] is False
    assert result["r92_created"] is False and result["real_money"]=="NO-GO"
    assert len(called)==16,(len(called),called)
    print("XRAY_SEC_CURRENT_SEVEN_MOCK=PASS_7_EXACT_ONE_ARCHIVE_NO_VENDOR_NO_PRIMARY")

def test_missing_contact():
    p,m=fixture()
    g=module.scope_contract(p,m,module.PRICE_SHA,module.MASTER_SHA)
    with patch.object(module,"load_source",return_value=g),patch.dict(os.environ,{"XRAY_SEC_USER_AGENT":""}):
        out=module.recheck(fetch=lambda *args:(_ for _ in ()).throw(AssertionError("NETWORK_WITHOUT_CONTACT")))
    assert out["status"]=="BLOCKED_OPERATOR_CONTACT" and not out["symbol_statuses"]
    print("XRAY_SEC_MISSING_OPERATOR=PASS_NO_NETWORK")

if __name__=="__main__":
    test_contract()
    test_network_mock()
    test_missing_contact()
