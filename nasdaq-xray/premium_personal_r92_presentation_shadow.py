#!/usr/bin/env python3
"""Turkish R92 alert formatter: no network, no candidates, no send, no orders.

Requires independently validated current canonical C4.17/R92 authority. These
booleans are input contracts, NOT independent proof. A calling task must fetch
and verify immutable sources and maintain its own persistent dedup ledger.
"""
import argparse
import datetime as dt
import json
import math
import re

SCHEMA="XRAY_PREMIUM_PERSONAL_R92_PRESENTATION_V1"
MATERIAL={
 "ENTRY_ZONE_APPROACHING":("🟡","GİRİŞ BÖLGESİNE YAKLAŞIYOR"),
 "ENTRY_ZONE_TOUCHED":("✅","GİRİŞ BÖLGESİNE TEMAS"),
 "ENTRY_ZONE_LEFT_ABOVE":("🚫","GİRİŞ ÜZERİNDE — KOVALAMA YOK"),
 "TARGET_LEVEL_TOUCHED":("✅","T1 HEDEFİNE TEMAS"),
 "STOP_LEVEL_TOUCHED":("🛑","STOP SEVİYESİNE TEMAS"),
 "INVALIDATED":("🔴","İPTAL — GEÇERSİZLİK"),
 "EXPIRED":("⌛","İPTAL — SÜRE DOLDU"),
 "OFFICIAL_HALT":("🚨","İPTAL — RESMÎ HALT"),
 "EVENT_VETO":("🔴","İPTAL — RESMÎ OLAY ENGELİ"),
 "AMBIGUOUS_INTRABAR_ORDER":("⚠️","HEDEF/STOP SIRASI BELİRSİZ"),
}
HIDDEN={"MONITORING","SOURCE_STALE"}

def need(value,code):
    if not value:raise ValueError("XRAY_PREMIUM_"+code)

def usd(value):
    need(type(value) in (int,float) and math.isfinite(value) and value>0,
         "NONFINITE_PRICE")
    return "$"+f"{value:,.2f}"

def date_utc(raw):
    need(type(raw) is str,"TIME_TYPE")
    try: t=dt.datetime.fromisoformat(raw.replace("Z","+00:00"))
    except ValueError as e:raise ValueError("XRAY_PREMIUM_TIME_PARSE") from e
    need(t.tzinfo is not None and t.utcoffset() is not None,"TIME_UNZONED")
    return t.astimezone(dt.timezone.utc).isoformat().replace("+00:00","Z")

def validate(candidate,authority):
    need(type(candidate) is dict and type(authority) is dict,"TYPE")
    need(authority.get("current_registered_r92") is True and
         authority.get("candidate_local_full_c417_proof") is True and
         authority.get("same_asof_immutable_chain_verified") is True and
         authority.get("actual_primary_data_verified") is True and
         authority.get("candidate_delivery_safety")=="PASS" and
         authority.get("simulation") is False,"INDEPENDENT_PROOF_REQUIRED")
    need(candidate.get("schema")=="XRAY_RESEARCH_CANDIDATE_R92_V1" and
         candidate.get("execution")=="NONE" and candidate.get("real_money")=="NO-GO",
         "R92_SCHEMA_OR_EXECUTION")
    ticker=candidate.get("symbol")
    need(type(ticker) is str and re.fullmatch(r"[A-Z][A-Z0-9.-]{0,9}",ticker),
         "INVALID_TICKER")
    key=candidate.get("delivery_key")
    need(type(key) is str and re.fullmatch(r"[A-Za-z0-9|:_\.-]{12,200}",key)
         and authority.get("registered_delivery_key")==key,"REGISTRY_KEY")
    fam=candidate.get("setup")
    need(fam in {"A","B","C","D"},"SETUP")
    asof=candidate.get("asof_et")
    need(type(asof) is str and
         dt.date.fromisoformat(asof).isoformat()==asof
         and authority.get("asof_et")==asof,"SOURCE_ASOF")
    created=date_utc(candidate.get("registered_at_utc"))
    vals={}
    for name in ("entry_low","entry_high","stop","chase_limit","r1","rr_basic","rr_severe"):
        v=candidate.get(name)
        need(type(v) in (int,float) and math.isfinite(v) and v>0,"NUMERIC_"+name)
        vals[name]=float(v)
    lo,hi,stop,chase,r1=(vals[k] for k in
                          ("entry_low","entry_high","stop","chase_limit","r1"))
    need(0<stop<lo<=hi<chase and r1>hi,"LEVEL_ORDER")
    need((hi-stop)/hi<=0.08000001,"RISK_GT8")
    min_basic,min_severe=(1.5,1.1) if fam=="A" else (2.0,1.5)
    max_rr=(r1-hi)/(hi-stop)
    need(vals["rr_basic"]>=min_basic and vals["rr_severe"]>=min_severe and
         vals["rr_severe"]<=vals["rr_basic"]<=max_rr+1e-9,"RR_GEOMETRY")
    extra=[]
    extras=candidate.get("independently_verified_targets") or {}
    need(type(extras) is dict and set(extras)<= {"T2","T3"},"TARGET_SCHEMA")
    previous=r1
    for k in ("T2","T3"):
        if k in extras:
            t=extras[k]
            need(type(t) is dict and t.get("verified") is True
                 and type(t.get("price")) in (int,float)
                 and math.isfinite(t["price"]) and t["price"]>previous,
                 "TARGET_UNVERIFIED_OR_NOT_ASCENDING")
            previous=t["price"]
            extra.append((k,t["price"]))
    url=authority.get("immutable_evidence_url")
    need(type(url) is str and re.fullmatch(
         r"https://github[.]com/gokaydonmez39-jpg/kripto-radar/"
         r"(?:blob|commit)/[a-f0-9]{40}(?:/[A-Za-z0-9._/-]+)?",url),
         "EVIDENCE_URL")
    return vals,created,extra,url

def render_buy(c,authority):
    v,t,extra,url=validate(c,authority)
    lines=[
      "🟢 AL — DOĞRULANMIŞ R92 | KİŞİSEL ARAŞTIRMA",
      f"📌 {c['symbol']} • Kurulum {c['setup']} • ASOF: {c['asof_et']} (ET)",
      f"🕒 Kaydedildi: {t}; gecikmeli veri, canlı işlem fiyatı DEĞİL",
      f"🟢 Giriş: {usd(v['entry_low'])} – {usd(v['entry_high'])}",
      f"🚫 Kovalamama sınırı: {usd(v['chase_limit'])}",
      f"🛑 Stop/iptal: {usd(v['stop'])}",
      f"🎯 T1/R1: {usd(v['r1'])}",
      f"⚖️ R/R temel {v['rr_basic']:.2f}x • ağır {v['rr_severe']:.2f}x",
    ]
    for k,x in extra:lines.append(f"🎯 {k}, ayrıca doğrulanmış: {usd(x)}")
    lines.extend([
      "✅ Kaynak, ASOF, resmî olay, kimlik ve C4.17 risk kanıtları kontrol edildi",
      f"🔐 R92: {c['delivery_key']}",
      f"🔎 Değişmez kanıt: {url}",
      "⚠️ Temas/dolum veya kâr garantisi yok; gecikme önemli olabilir",
      "🧭 Kişisel karar desteği. Broker/emir/gerçek para işlemi YOK.",
    ])
    return "\n".join(lines)

def render_followup(c,row,authority):
    validate(c,authority)
    need(type(row) is dict and
         row.get("schema")=="XRAY_MANUAL_RESEARCH_FOLLOWUP_SHADOW_V1" and
         row.get("symbol")==c["symbol"] and
         row.get("delivery_key")==c["delivery_key"] and
         row.get("research_only") is True and
         row.get("execution")=="NONE" and row.get("real_money")=="NO-GO" and
         row.get("user_notification_delivered") is False,
         "LIFECYCLE_IDENTITY_OR_DELIVERY")
    status=row.get("status")
    need(type(status) is str and status in set(MATERIAL)|HIDDEN,"STATE")
    if status in HIDDEN:return None
    key=row.get("alert_dedup_key")
    need(row.get("alert") is True and row.get("transition")==status and
         type(key) is str and re.fullmatch(r"[a-f0-9]{64}",key) and
         authority.get("lifecycle_transition_independently_rechecked") is True
         and authority.get("alert_key_previously_delivered") is False,
         "FOLLOWUP_AUTHORITY_OR_DUPLICATE")
    ico,title=MATERIAL[status]
    lines=[f"{ico} XRAY {title} — {c['symbol']}",
           f"📅 Kanıt saati: {date_utc(row.get('asof_observed_utc'))}",
           f"🟢 Giriş: {usd(c['entry_low'])}–{usd(c['entry_high'])}",
           f"🛑 Stop: {usd(c['stop'])} • 🎯 T1: {usd(c['r1'])}"]
    if status=="TARGET_LEVEL_TOUCHED":
        lines.append("✅ T1'e TEMAS; gerçek pozisyon veya kâr kanıtı DEĞİL.")
    if status=="STOP_LEVEL_TOUCHED":
        lines.append("🛑 Stop temas: iptal/riski yeniden değerlendir; gerçekleşmiş zarar kanıtı değil.")
    if status=="AMBIGUOUS_INTRABAR_ORDER":
        lines.append("⚠️ Aynı barda stop ve hedef; önce hangisi bilinmiyor. Kâr yazma.")
    if status in ("INVALIDATED","EXPIRED","OFFICIAL_HALT","EVENT_VETO"):
        lines.append("🔴 Bu adayın yaşam döngüsü KAPANDI; otomatik yeniden AL yapılamaz.")
    lines.extend([f"🔐 Tekil güncelleme: {key}",
                  "🧭 Sadece kayıtlı R92 takibi; emir ve telefon teslim alındısı yok."])
    return "\n".join(lines)

def selftest():
    c={"schema":"XRAY_RESEARCH_CANDIDATE_R92_V1","symbol":"TEST",
       "delivery_key":"TEST|A|SYNTHETIC_001","setup":"A",
       "asof_et":"2026-10-19","registered_at_utc":"2026-10-20T01:00:00Z",
       "entry_low":100.0,"entry_high":101.0,"stop":95.0,
       "chase_limit":102.0,"r1":115.0,"rr_basic":2.0,"rr_severe":1.2,
       "execution":"NONE","real_money":"NO-GO"}
    a={"current_registered_r92":True,"candidate_local_full_c417_proof":True,
       "same_asof_immutable_chain_verified":True,"actual_primary_data_verified":True,
       "candidate_delivery_safety":"PASS","simulation":False,
       "registered_delivery_key":c["delivery_key"],"asof_et":c["asof_et"],
       "immutable_evidence_url":
          "https://github.com/gokaydonmez39-jpg/kripto-radar/commit/"+"a"*40,
       "lifecycle_transition_independently_rechecked":True,
       "alert_key_previously_delivered":False}
    b={"schema":"XRAY_MANUAL_RESEARCH_FOLLOWUP_SHADOW_V1",
       "symbol":"TEST","delivery_key":c["delivery_key"],
       "status":"TARGET_LEVEL_TOUCHED","transition":"TARGET_LEVEL_TOUCHED",
       "alert":True,"alert_dedup_key":"b"*64,
       "asof_observed_utc":"2026-10-20T20:00:00Z",
       "research_only":True,"execution":"NONE","real_money":"NO-GO",
       "user_notification_delivered":False}
    need(render_buy(c,a).startswith("🟢 AL"),"POSITIVE_BUY")
    need("T1'e TEMAS" in render_followup(c,b,a),"POSITIVE_TARGET")
    need(render_followup(c,{**b,"status":"SOURCE_STALE"},a) is None,
         "SOURCE_STALE_NOT_USER_VISIBLE")
    invalid=[
     ("NO_R92",{**a,"current_registered_r92":False},c,b),
     ("NO_PRIMARY",{**a,"actual_primary_data_verified":False},c,b),
     ("NO_LOCAL",{**a,"candidate_local_full_c417_proof":False},c,b),
     ("SIMULATED",{**a,"simulation":True},c,b),
     ("KEY",{**a,"registered_delivery_key":"forged"},c,b),
     ("ASOF",{**a,"asof_et":"2026-10-18"},c,b),
     ("UNTRUSTED_URL",{**a,"immutable_evidence_url":"https://evil.invalid"},c,b),
     ("STOP",a,{**c,"stop":100.5},b),
     ("RISK",a,{**c,"stop":90.0},b),
     ("RR",a,{**c,"rr_basic":4.0},b),
     ("T2",a,{**c,"independently_verified_targets":
              {"T2":{"price":120.0,"verified":False}}},b),
     ("TICKER",a,{**c,"symbol":"SELL!"},b),
     ("DEDUPE",{**a,"alert_key_previously_delivered":True},c,b),
     ("HASH",a,c,{**b,"alert_dedup_key":"z"*64}),
     ("TRANSITION",a,c,{**b,"transition":"INVALIDATED"}),
     ("RECEIPT",a,c,{**b,"user_notification_delivered":True}),
     ("RECHECK",{**a,"lifecycle_transition_independently_rechecked":False},c,b),
    ]
    for name,auth,cand,evt in invalid:
        try:
            render_buy(cand,auth)
            render_followup(cand,evt,auth)
        except ValueError:
            continue
        raise RuntimeError("XRAY_PREMIUM_FAIL_OPEN_"+name)
    need(len(invalid)==17,"COUNT")
    print("XRAY_PREMIUM_R92_FORMAT_SELFTEST=PASS_17_NEGATIVES_NO_USER_DELIVERY")

def demo():
    print("🧪 XRAY DEMO — GERÇEK AL SİNYALİ DEĞİL")
    print("📌 Hisse: [ÖRNEK] • Setup: [KANITLI A/B/C/D]")
    print("🕒 ASOF/gecikme: [DOĞRULANMIŞ]")
    print("🟢 Giriş: [DOĞRULANMIŞ BANT]")
    print("🚫 Kovalamama: [GEÇERLİ ÜST SINIR]")
    print("🛑 Stop/iptal: [KANITLI SEVİYE]")
    print("🎯 T1 ✅ / T2 ⏳ / T3 ⏳ — yalnızca kanıtlı seviyeler")
    print("⚖️ R/R, olay takvimi, SHA, kaynak bağlantısı: [KANITLI]")
    print("🚨 Stop/hedef/iptal takip: ancak yeni resmî veriye dayalı olay olursa")
    print("📵 Demo telefon bildirimi, AL veya emir GÖNDERMEZ.")

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--demo",action="store_true")
    args=p.parse_args()
    need(args.selftest != args.demo,"EXACTLY_ONE_MODE")
    if args.selftest:selftest()
    else:demo()
