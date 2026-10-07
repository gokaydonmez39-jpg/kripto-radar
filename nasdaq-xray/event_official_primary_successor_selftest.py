#!/usr/bin/env python3
import event_official_primary_successor_builder as b
H=["2026-10-07","2026-10-08","2026-10-09","2026-10-12","2026-10-13","2026-10-14","2026-10-15","2026-10-16"]
def r(st,d,basis="TITLE_EXPLICIT_FUTURE_DATE",identity=True):
    return {"status":st,"selected_event_date":d,"issuer_probes":[{"identity_validated":identity,"matches":[{
      "event_date":d,"horizon_result":"INSIDE_EXACT_8_SESSION_HORIZON" if d in H else "OUTSIDE_EXACT_8_SESSION_HORIZON",
      "authority":"ISSUER_IR_PRIMARY","source_url":"https://ir.example.com/release","extraction_basis":basis}]}]}
def main():
    x=b.candidate_promotion("A",r("CLEAN_OUTSIDE_HORIZON_CANDIDATE","2026-10-27"),"UNKNOWN",H); assert x and x["classification"]=="CLEAN_DISCOVERY"
    x=b.candidate_promotion("B",r("BLOCK_CONFIRMED_8SESSION_CANDIDATE","2026-10-14"),"UNKNOWN",H); assert x and x["classification"]=="BLOCK_CONFIRMED_8SESSION"
    assert b.candidate_promotion("C",r("CLEAN_OUTSIDE_HORIZON_CANDIDATE","2026-10-27"),"CLEAN_DISCOVERY",H) is None
    assert b.candidate_promotion("D",r("CLEAN_OUTSIDE_HORIZON_CANDIDATE","2026-10-27","BASE_PAGE_SCHEDULE_SENTENCE_EXPLICIT_FUTURE_DATE"),"UNKNOWN",H) is None
    assert b.candidate_promotion("E",r("BLOCK_CONFIRMED_8SESSION_CANDIDATE","2026-10-27"),"UNKNOWN",H) is None
    m=r("CLEAN_OUTSIDE_HORIZON_CANDIDATE","2026-10-27"); m["issuer_probes"][0]["matches"].append({
      "event_date":"2026-10-14","horizon_result":"INSIDE_EXACT_8_SESSION_HORIZON","authority":"ISSUER_IR_PRIMARY",
      "source_url":"https://ir.example.com/other","extraction_basis":"TITLE_EXPLICIT_FUTURE_DATE"})
    assert b.candidate_promotion("F",m,"UNKNOWN",H) is None
    print("EVENT_OFFICIAL_PRIMARY_SUCCESSOR_SELFTEST=PASS")
if __name__=="__main__": main()
