"""Pure private EOD/score/Kronos V2 ledger readback contract.

No network, writes, logs, secrets or notification authority. Caller must
independently verify XNAS completion, source run/jobs, expected PIT order and
algorithm SHA, authenticated private Sheets identity and complete ranges.
Hashes here detect inconsistent content, not malicious re-signing.
"""
from __future__ import annotations
from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re

SCAN_HEADER=("ASOF ET","ÜRETİM KANALI","İSTENEN","İŞLENEN","GEÇERLİ","EKSİK","FINAL READY","YENİ KAYIT","RUN KANITI","DURUM / VERİ SINIRI")
SCORE_HEADER=("KAYIT_KIMLIGI","ASOF_ET","EPIZOT_KIMLIGI","SEMBOL","KAYIT_TIPI","SIRA","SKOR_100","TREND_20","RSI_15","RVOL_15","REL_GUC_15","LIKIDITE_10","RISK_15","FIYAT_YAPISI_10","GUNCEL_IEX_CLOSE_USD","ORIJINAL_REFERANS_USD","ORIJINAL_STOP_USD","ORIJINAL_HEDEF_2R_USD","TEORIK_DEGISIM_YUZDE","STOPA_MESAFE_YUZDE","HEDEFE_MESAFE_YUZDE","TAKIP_SEANSI","RSI14","RVOL20","20SEANS_GETIRI_YUZDE","RISK_NOTU","KANIT_URL","BILDIRIM_DURUMU","BILDIRIM_ZAMANI_TR","KAYIT_SHA256","KAPSAM_SHA256","ALGORITMA_SHA256","SKOR_SURUMU","ORT_IEX_DOLAR_HACMI","ATR_RISK_YUZDE")
KRONOS_HEADER=("KAYIT_KIMLIGI","ASOF_ET","SEMBOL","UFUK_SEANS","SON_IEX_KAPANIS_USD","TAHMIN_KAPANIS_USD","TAHMIN_GETIRI_PCT","MODEL_ID","MODEL_REVIZYON","TOKENIZER_REVIZYON","KRONOS_KOD_REVIZYON","EVREN_SHA256","POLITIKA_SHA256","TARAMA_KAYIT_KIMLIGI","GIRDI_SHA256","TAHMIN_SHA256","MODUL_SURUMU","DURUM","VERI_POLITIKASI","KAYIT_SHA256")
MODEL=("NeoQuasar/Kronos-small","901c26c1332695a2a8f243eb2f37243a37bea320","0e0117387f39004a9016484a186a908917e22426","67b630e67f6a18c9e9be918d9b4337c960db1e9a")
VERSION="XRAY_KRONOS_CLOSE_ONLY_V2_20261107"
SCORE_VERSION="XRAY_SWING_SCORE_V1_20261105"
SOURCE_URL="https://github.com/gokaydonmez39-jpg/kripto-radar/actions/runs/"
HORIZONS=("1","5","12")

def _require(ok,code):
    if not ok: raise ValueError(code)

def _day(v):
    _require(type(v) is str,"INVALID_DAY")
    try: d=date.fromisoformat(v)
    except ValueError: raise ValueError("INVALID_DAY") from None
    _require(d.isoformat()==v,"INVALID_DAY")
    return v

def _sha(v):
    _require(type(v) is str and re.fullmatch("[0-9a-f]{64}",v) is not None,"INVALID_SHA")
    return v

def _count(v):
    _require(type(v) is str and re.fullmatch("0|[1-9][0-9]*",v) is not None,"INVALID_COUNT")
    return int(v)

def _decimal(v,positive=False):
    _require(type(v) is str and len(v)<=40 and re.fullmatch(r"-?[0-9]+(?:\.[0-9]+)?",v) is not None,"INVALID_DECIMAL")
    try: x=Decimal(v)
    except InvalidOperation: raise ValueError("INVALID_DECIMAL") from None
    _require(x.is_finite() and (not positive or x>0),"INVALID_DECIMAL")
    return x

def canonical_sha(v):
    return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()).hexdigest()

def scope_sha(symbols):
    return hashlib.sha256(("\n".join(symbols)+"\n").encode()).hexdigest()

def _matrix(matrix,header,cap):
    _require(type(matrix) is list and 1<=len(matrix)<=cap and tuple(matrix[0])==header,"HEADER_OR_CAPACITY")
    out=[]; blank=False; keys=set()
    for raw in matrix[1:]:
        _require(type(raw) is list and len(raw)<=len(header) and all(type(x) is str for x in raw),"ROW_SCHEMA")
        if not raw or all(x=="" for x in raw):
            blank=True; continue
        _require(not blank and bool(raw[0]) and raw[0] not in keys,"BLANK_OR_DUPLICATE_ROW")
        keys.add(raw[0]);out.append(raw+[""]*(len(header)-len(raw)))
    return out

def build_readback(scan_matrix,score_matrix,kronos_matrix,*,expected_asof,expected_symbols,expected_algorithm_sha,expected_run_id):
    """Return in-memory research display records only; never publish or certify live.
    No complete per-symbol scan classifications or native OHLC paths exist in
    these ledgers. Do not manufacture them. Score records are episode-based.
    """
    day=_day(expected_asof)
    _require(type(expected_symbols) in (list,tuple) and len(expected_symbols)==477 and
             all(type(s) is str and re.fullmatch(r"[A-Z0-9.]+",s) for s in expected_symbols) and
             len(set(expected_symbols))==477,"CANONICAL_SCOPE_REQUIRED")
    symbols=set(expected_symbols);scope=scope_sha(expected_symbols);algo=_sha(expected_algorithm_sha)
    _require(type(expected_run_id) is str and re.fullmatch("[1-9][0-9]{0,20}",expected_run_id),"INVALID_RUN")
    url=SOURCE_URL+expected_run_id
    scans=_matrix(scan_matrix,SCAN_HEADER,20000)
    _require(bool(scans) and scans[-1][0]==day and sum(r[0]==day for r in scans)==1,"SCAN_ASOF")
    scan=scans[-1]
    _require(scan[1] in ("GitHub schedule VERIFIED IEX EOD","GitHub workflow_dispatch VERIFIED IEX EOD") and scan[2:7]==["477","477","477","0","TRUE"] and scan[8]==url,"SCAN_NOT_ACCEPTED")
    _count(scan[7])
    parts=[p.strip() for p in scan[9].split(";")]
    for label,want in (("scopeSHA",scope),("algorithmSHA",algo)):
        hits=[p[len(label)+1:] for p in parts if p.startswith(label+"=")]
        _require(hits==[want],"SCAN_HASH_MISMATCH")
    all_scores=_matrix(score_matrix,SCORE_HEADER,50000)
    _require(all(_day(r[1])<=day for r in all_scores),"FUTURE_SCORE")
    scores=[r for r in all_scores if r[1]==day]
    summaries=[r for r in scores if r[4]=="SUMMARY"]
    _require(len(summaries)==1,"SUMMARY_COUNT")
    summary=summaries[0]
    _require(summary[0]==day+"|SUMMARY" and summary[2:4]==["",""] and summary[27] in ("READY_FOR_CHATGPT_DAILY_DIGEST","REQUESTED_NOT_DEVICE_ACK") and summary[7]=="0","SUMMARY_NOT_READY")
    n=_count(summary[5]);_require(n==_count(summary[6]),"SUMMARY_HOLD")
    digest=_sha(summary[29]);episodes=[];ranks=set();epkeys=set()
    for r in scores:
        _require(r[26]==url and r[29:33]==[digest,scope,algo,SCORE_VERSION],"SCORE_PROVENANCE")
        if r[4]=="SUMMARY": continue
        _require(r[4]=="EPISODE" and r[3] in symbols and r[0]==day+"|"+r[2] and r[2] not in epkeys,"EPISODE_ID")
        epday,sep,epsym=r[2].partition("|")
        _require(sep=="|" and epsym==r[3] and _day(epday)<=day,"EPISODE_ID")
        rank=_count(r[5]);score=_count(r[6])
        _require(1<=rank<=n and rank not in ranks and score<=100,"RANK_OR_SCORE")
        ref,stop,target=(_decimal(r[i],True) for i in (15,16,17))
        _require(stop<ref<target and abs((target-ref)-2*(ref-stop))<=Decimal("0.004"),"FIXED_BRACKET")
        _require(_count(r[21])<=15,"EPISODE_HORIZON")
        ranks.add(rank);epkeys.add(r[2])
        episodes.append({"episode_id":r[2],"symbol":r[3],"rank":rank,"technical_score":score,"reference":r[15],"stop":r[16],"target_2r":r[17]})
    _require(len(episodes)==n and len(scores)==n+1 and _count(summary[8])==len({x["symbol"] for x in episodes}),"SCORE_COHORT")
    ledger=_matrix(kronos_matrix,KRONOS_HEADER,40000)
    current=[];group={}
    for r in ledger:
        rd=_day(r[1]);_require(rd[:7]==day[:7] and rd<=day,"PARTITION_EPOCH")
        _require(r[3] in HORIZONS and r[0]==f"{rd}|{r[2]}|H{r[3]}" and r[19]==canonical_sha(r[:19]) and r[16]==VERSION,"ROW_HASH_OR_ID")
        if rd!=day: continue
        _require(r[2] in symbols and tuple(r[7:11])==MODEL and r[11:14]==[scope,algo,day],"KRONOS_PROVENANCE")
        _sha(r[14]);reference=_decimal(r[4],True);quality=r[17]
        if quality in ("RESEARCH_ONLY","RESEARCH_CLOSE_ONLY"):
            forecast=_decimal(r[5],True);_decimal(r[6]);_sha(r[15])
            policy="IEX_RAW_AMOUNT_OHLC_MEAN_VOLUME_PROXY" if quality=="RESEARCH_ONLY" else "RAW_CLOSE_ONLY__NATIVE_OHLC_GEOMETRY_INVALID"
            _require(r[18]==policy,"KRONOS_QUALITY_POLICY")
            # Forecast return is computed from unrounded prices upstream.
            # Check the stored values with a conservative rounding interval.
            q=Decimal("0.0000005")
            if reference>q:
                low=((max(Decimal(0),forecast-q)/(reference+q))-1)*100-q
                high=(((forecast+q)/(reference-q))-1)*100+q
                _require(low<=_decimal(r[6])<=high,"FORECAST_RETURN_MISMATCH")
            kind="FORECAST_CLOSE_POINTS"
        else:
            _require(re.fullmatch(r"HOLD_QC_[A-Z0-9_]+",quality) and r[5]==r[6]==r[15]=="" and r[18]=="MODEL_OUTPUT_UNUSABLE","HOLD_HAS_FORECAST")
            kind="NONE"
        # Model quality can be native-valid, but this ledger stores CLOSE only.
        fingerprint=(r[4],r[14],r[15],quality,r[18])
        previous=group.setdefault(r[2],(fingerprint,set()))
        _require(previous[0]==fingerprint and r[3] not in previous[1],"HORIZON_GROUP_DRIFT")
        previous[1].add(r[3])
        current.append({"symbol":r[2],"horizon":int(r[3]),"model_quality":quality,"chart_kind":kind,"close":r[5] or None,"native_ohlc":None})
    _require(len(current)==1431 and set(group)==symbols and all(h==set(HORIZONS) for _,h in group.values()),"KRONOS_COHORT")
    return {"schema":"XRAY_PRIVATE_RESEARCH_READBACK_V1","asof":day,"scope_sha":scope,"algorithm_sha":algo,"source_run_id":expected_run_id,"score_digest_consistency_only":digest,"scope_count":477,"score_count":n,"forecast_count":1431,"episodes":episodes,"forecasts":current,"source_authentication":"CALLER_WITNESS_NOT_ATTESTED","scan_classifications_available":False,"native_forecast_ohlc_available":False,"may_publish":False,"may_notify":False,"may_modify_al":False,"may_trade":False}
