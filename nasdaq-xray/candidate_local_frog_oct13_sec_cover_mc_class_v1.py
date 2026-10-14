#!/usr/bin/env python3
"""FROG issuer ordinary-share 10-Q cover vs real Oct13 SIP close (not PIT MC PRIMARY)."""
from __future__ import annotations
import argparse,datetime as dt,hashlib,json,os,re
from pathlib import Path
from zoneinfo import ZoneInfo
import build_candidate_legal_guard as legal
import sec_official_free_mc_transport_probe as sec
from candidate_local_frog_oct13_pit_reconciliation_v1 import fetch_price,sessions
ROOT=Path(__file__).resolve().parent
ASOF="2026-10-13"
URL="https://www.sec.gov/Archives/edgar/data/1800667/000119312526340294/frog-20260630.htm"
ACC="0001193125-26-340294"
CIK="0001800667"
def need(ok,why):
    if not ok:raise ValueError("XRAY_FROG_SEC_COVER_"+why)
def parse_cover(text):
    import html
    flat=re.sub(r"\s+"," ",html.unescape(re.sub(r"(?s)<[^>]*>"," ",text))).lower()
    cls=("ordinary shares, nis 0.01 par value" in flat and
         "frog" in flat and "nasdaq global select market" in flat)
    hits=re.findall(
        r"as of july 31, 2026, the registrant had\s+([\d,]+)\s+ordinary shares",
        flat)
    need(cls and len(hits)==1,"EXACT_CLASS_AND_COVER")
    shares=int(hits[0].replace(",",""))
    need(shares>0,"POSITIVE_SHARES")
    return shares
def accession_pit(sub):
    idx=sec.accession_acceptance_index(sub)
    v=idx.get(ACC)
    need(v is not None and v["form"]=="10-Q" and v["filed"]=="2026-08-07",
         "EXACT_ACCESSION")
    accepted=dt.datetime.fromisoformat(v["accepted_at"].replace("Z","+00:00"))
    # Older acceptance is unambiguously before Oct13 on either possible ET/UTC clock.
    need(accepted.tzinfo is not None and
         accepted.astimezone(dt.timezone.utc) <
         sec.official_nasdaq_close_utc(ASOF)-dt.timedelta(days=60),
         "PRE_ASOF_ACCEPTANCE")
    return v["filed"]
def price_asof(bars):
    seen=[]
    for b in bars:
        t=dt.datetime.fromisoformat(str(b["t"]).replace("Z","+00:00"))
        if t.astimezone(ZoneInfo("America/New_York")).date().isoformat()==ASOF:
            need(type(b.get("c")) in (int,float) and
                 0<b["c"]<1e6,"ASOF_POSITIVE_PRICE")
            seen.append(b["c"])
    need(len(seen)==1,"EXACT_ASOF_DAILY_CLOSE")
    return seen[0]
def selftest():
    body=("Ordinary Shares, NIS 0.01 par value FROG The Nasdaq Global Select Market "
          "As of July 31, 2026, the registrant had 123,301,311 ordinary shares")
    need(parse_cover(body)==123301311,"KNOWN_COVER_TEST")
    for tamper in (body.replace("FROG","WRONG"),body.replace("123,301,311","0"),
                   body.replace("July 31","August 31")):
        try:parse_cover(tamper)
        except ValueError:pass
        else:raise AssertionError("TAMPERED_COVER_ACCEPTED")
    print("XRAY_FROG_SEC_COVER_CLASS_SELFTEST=PASS_3_TAMPER_VETO")
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--out",type=Path)
    p.add_argument("--selftest",action="store_true")
    a=p.parse_args()
    if a.selftest:return selftest()
    need(a.out and not a.out.resolve().is_relative_to(ROOT.parent.resolve()),"OUTPUT_EPHEMERAL")
    r={"schema":"XRAY_FROG_OCT13_CLASS_SPECIFIC_10Q_COVER_AND_SIP_MC_SHADOW_V1",
       "asof_et":ASOF,"symbol":"FROG","official_sec_cover_url":URL,
       "official_sec_accession":ACC,"current_sec_cover_status":"UNKNOWN",
       "market_cap_status":"UNKNOWN_NOT_CALCULATED",
       "price_source_status":"UNKNOWN","source_asof_pit":False,
       "class_aware_exact_asof_shares":False,
       "total_issuer_share_classes_reconciled":False,
       "corporate_actions_pit_reconciled":False,
       "exact_corrected_rth_close_attested":False,
       "mc_primary_ge_2b":False,"r92_registered":0,
       "canonical_modified":False,"iphone_push_receipt_attested":False,
       "raw_alpaca_quotes_persisted":False,
       "real_money":"NO-GO","execution":"NONE","unknown_never_pass":True}
    def save():a.out.write_text(json.dumps(r,sort_keys=True,indent=2)+chr(10))
    save()
    ua=os.getenv("XRAY_SEC_USER_AGENT","")
    key=(os.getenv("XRAY_ALPACA_DATA_KEY_ID") or os.getenv("XRAY_ALPACA_API_KEY_ID") or "")
    secret=(os.getenv("XRAY_ALPACA_DATA_SECRET_KEY") or os.getenv("XRAY_ALPACA_API_SECRET_KEY") or "")
    try:
        need(sec.valid_operator_contact(ua),"SEC_CONTACT")
        sub=sec.get_json("https://data.sec.gov/submissions/CIK"+CIK+".json",ua)
        acceptance_date=accession_pit(sub)
        source=legal._fetch(URL,limit=5_000_000)
        cover_shares=parse_cover(source.decode("utf-8","replace"))
        r.update({"current_sec_cover_status":"OFFICIAL_CLASS_COVER_JUL31_VERIFIED",
                  "sec_cover_shares_observation_date":"2026-07-31",
                  "sec_filing_date":acceptance_date,
                  "cover_tradable_security_class":"Ordinary shares, NIS 0.01 par value",
                  "cover_shares_observed":cover_shares,
                  "historical_sec_class_cover_verified":True})
    except Exception as e:
        r["current_sec_cover_status"]="UNKNOWN_SEC_DOC_OR_PIT"
        r["sec_error_type"]=type(e).__name__
        save()
        print("XRAY_FROG_SEC_COVER="+r["current_sec_cover_status"])
        return
    save()
    try:
        need(bool(key and secret),"ALPACA_ACCESS")
        _,d=sessions()
        count=[0]
        raw=fetch_price("1Day","raw",d,key,secret,count)
        adjusted=fetch_price("1Day","all",d,key,secret,count)
        rp,ap=price_asof(raw),price_asof(adjusted)
        need(abs(rp-ap)<1e-6,"RAW_ADJUSTED_CURRENT_PRICE_DIFFER")
        # This arithmetic is an INDICATIVE vintage cover MC, not an exact Oct13
        # issuer-share-class PIT capitalization; later issuances/repurchases and
        # closing tape corrections can change it. Never mark MC PRIMARY here.
        estimate=cover_shares*rp
        r.update({"price_source_status":"ALPACA_RAW_AND_ALL_SIP_1DAY_ASOF_OBSERVED",
                  "observed_vintage_cap_ge_2b_shadow":estimate>=2_000_000_000,
                  "observed_vintage_cap_band":
                      "GE_10B_SHADOW" if estimate>=10_000_000_000 else
                      ("GE_2B_SHADOW" if estimate>=2_000_000_000 else "LT_2B_SHADOW"),
                  "market_cap_status":"INDICATIVE_ASOF_PRICE_X_STALE_JUL31_CLASS_SHARES_NOT_PRIMARY",
                  "price_sip_calls":count[0]})
    except Exception as e:
        r["price_source_status"]="UNKNOWN_PRICE_OR_CORRECTIONS"
        r["price_error_type"]=type(e).__name__
    save()
    print("XRAY_FROG_SEC_COVER="+r["current_sec_cover_status"])
    print("XRAY_FROG_VINTAGE_MC_STATUS="+r["market_cap_status"])
    print("XRAY_FROG_VINTAGE_MC_BAND="+str(r.get("observed_vintage_cap_band","UNKNOWN")))
    print("XRAY_FROG_MC_PRIMARY=0_NO_CLASS_ASOF_CORRECTION_ATTESTATION")
if __name__=="__main__":
    main()
