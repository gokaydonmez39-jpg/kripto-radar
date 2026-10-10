#!/usr/bin/env python3
"""Independent synthetic Longbridge MC research regression; zero live vendor calls."""
import copy,hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import longbridge_quote_shadow_contract as m

def main():
    scope=m.current_scope()
    assert scope["asof_et"]=="2026-10-09"
    assert scope["price_blob_sha"]=="6f3f68fff0897d68f200ad3621c51a5071494714"
    assert scope["master_blob_sha"]=="828c21436a836b69fe5084387e1c54446c7b5075"
    assert len(scope["symbols"])==514
    rows=[{"symbol":s+".US","total_market_value":("2300000000" if i<498 else "1900000000")}
          for i,s in enumerate(scope["symbols"])]
    out=m.telemetry(scope,rows,source_rights_attested=False)
    assert out["coverage"]==514 and out["above_2b"]==498 and out["below_2b"]==16
    assert out["source_rights_attested"] is False
    assert out["source_market_cap_asof_attested"] is False
    assert out["date_filtered_market_cap_available"] is False
    assert out["primary_mc_pass_created"] is False
    assert out["candidate_created"] is False
    assert out["r92_created"] is False
    assert out["unknown_never_pass"] is True
    assert out["execution"]=="NONE" and out["real_money"]=="NO-GO"
    assert out["status"]=="SHADOW_ONLY_PRIMARY_BLOCKED_RIGHTS_AND_PIT"
    assert "AAPL.US" not in json.dumps(out) and "2300000000" not in json.dumps(out)
    # Passing a rights boolean must NOT convert undated market cap into
    # primary evidence. Official docs expose NO as-of field for CalcIndex.
    with_rights=m.telemetry(scope,rows,source_rights_attested=True)
    assert with_rights["status"]=="SHADOW_ONLY_PRIMARY_BLOCKED_PIT"
    assert with_rights["primary_mc_pass_created"] is False
    negatives=[
      ([*rows,rows[0]],"duplicate"),
      ([*rows[:-1],{"symbol":"WRONG.US","total_market_value":"2000000000"}],"outside_scope"),
      ([{"symbol":scope["symbols"][0]+".US","total_market_value":"NaN"},*rows[1:]],"nan"),
      ([{"symbol":scope["symbols"][0]+".US","total_market_value":True},*rows[1:]],"bool"),
      ([{"symbol":scope["symbols"][0]+".US","total_market_value":"-1"},*rows[1:]],"negative"),
      ([{"symbol":scope["symbols"][0]+".US","total_market_value":"0"},*rows[1:]],"zero"),
      ([{"symbol":scope["symbols"][0]+".US","total_market_value":"Infinity"},*rows[1:]],"inf"),
      (rows[:-1],"missing"),
      ([{"symbol":scope["symbols"][0]+".US","total_market_value":None},*rows[1:]],"null"),
    ]
    for mutated,label in negatives:
      invalid=m.telemetry(scope,mutated,source_rights_attested=True)
      assert invalid["primary_mc_pass_created"] is False,label
      assert invalid["status"]!="SHADOW_ONLY_PRIMARY_BLOCKED_PIT",label
      assert invalid["observed_complete"] is False,label
    assert m.rights_attested({}) is False
    assert m.rights_attested({"XRAY_LONGBRIDGE_NONDISPLAY_LICENSE_OK":"true"}) is False
    assert m.rights_attested({"XRAY_LONGBRIDGE_NONDISPLAY_LICENSE_OK":"true","XRAY_LONGBRIDGE_LICENSE_GRANT_SHA256":"a"*64}) is True
    # Fake claim of provider as-of timestamp is never accepted even with rights.
    tampered=copy.deepcopy(rows)
    tampered[0]["asof_et"]="2026-10-09"
    assert m.telemetry(scope,tampered,source_rights_attested=True)["primary_mc_pass_created"] is False
    print("XRAY_LONGBRIDGE_514_SYNTHETIC_SCOPE=PASS_498_16_10_NEGATIVES_NO_PRIMARY_NO_VENDOR_HTTP")

if __name__=="__main__":
    main()
