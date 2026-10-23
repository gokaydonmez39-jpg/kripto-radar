#!/usr/bin/env python3
"""FISV ticker-continuity and CCC 260-session SIP presence research. No PRICE/G9/R92 authority.

Bounded GitHub runner research: current root ASOF only; no raw vendor data
persisted, no broker/order endpoints. This does NOT validate exact RTH volume,
CA/PIT, provider unattended usage-rights, MC, or trade corrections.
"""
from __future__ import annotations
import argparse, datetime as dt, json, math, os, re, urllib.error, urllib.parse, urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

SCHEMA='XRAY_V33_TWO_SYMBOL_SIP_260_SHADOW_V1'
ROOT=Path(__file__).resolve().parent
SYMBOLS=('FISV','CCC')
MAX_PAGES=3
MAX_BODY=3_000_000
NY=ZoneInfo('America/New_York')
UTC=dt.timezone.utc
CHANGE='2025-11-11'  # Nasdaq official FISV transfer from NYSE symbol FI

class Blocked(Exception):pass

def need(p,code):
    if not p:raise Blocked('XRAY_V33_'+code)

def stamp(s):
    need(isinstance(s,str),'TIMESTAMP_NOT_STRING')
    try:d=dt.datetime.fromisoformat(s.replace('Z','+00:00'))
    except ValueError:raise Blocked('XRAY_V33_TIME_PARSE')
    need(d.tzinfo is not None,'TIME_UNZONED')
    return d.astimezone(NY).date().isoformat()

def summarize(expected,bars,weeks):
    need(type(expected) is list and len(expected)==260 and len(set(expected))==260
         and expected==sorted(expected),'CALENDAR_INTEGRITY')
    need(type(weeks) is list and len(weeks)==52 and len(set(weeks))==52
         and weeks==sorted(weeks) and set(weeks).issubset(expected),
         'OFFICIAL_52_WEEK_CLOSE_SCOPE')
    need(type(bars) is dict and set(bars).issubset(SYMBOLS),'SOURCE_SYMBOL_SCOPE')
    proof={}
    for sym in SYMBOLS:
        seen=set(); invalid=0; duplicate=0; outside=0
        for row in bars.get(sym,[]):
            need(type(row) is dict,'ROW_NOT_OBJECT')
            day=stamp(row.get('t',''))
            if day not in expected:outside+=1;continue
            if day in seen:duplicate+=1
            seen.add(day)
            try:prices=[row[k] for k in ('o','h','l','c')];vol=row['v']
            except KeyError:invalid+=1;continue
            if not (all(type(x) in (int,float) and math.isfinite(x) and x>0 for x in prices)
                    and type(vol) in (int,float) and math.isfinite(vol) and vol>0
                    and vol==int(vol) and prices[2]<=min(prices[0],prices[3])
                    and prices[1]>=max(prices[0],prices[2],prices[3])):invalid+=1
        missing=len(set(expected)-seen)
        proof[sym]={'expected':260,'observed':len(seen),'missing':missing,
                    'completed_week_closes_expected':52,
                    'completed_week_closes_observed':len(set(weeks)&seen),
                    'research_52_completed_weeks_present':len(set(weeks)&seen)==52,
                    'invalid':invalid,'duplicate':duplicate,'outside':outside,
                    'research_exact260_present':missing==0 and invalid==0 and duplicate==0}
    proof['FISV']['legacy_FI_date_scope_exists']=sum(day<CHANGE for day in expected)>0
    proof['FISV']['legacy_FI_expected_sessions']=sum(day<CHANGE for day in expected)
    return proof

def report(asof,stats=None,status='BLOCKED',pages=0):
    return {'schema':SCHEMA,'asof_et':asof,'status':status,'symbol_counts':stats or {},
            'symbol_scope':['FISV','CCC'],'expected_sessions':260,
            'sip_pages_used':pages,'sip_max_pages':MAX_PAGES,
            'historical_FISV_FI_issuer_continuity_claim':'OFFICIAL_NASDAQ_LISTING_2025_11_11_AND_PROVIDER_ASOF_MAPPING_RESEARCH',
            'research_presence_only':True,
            'corporate_actions_adjustments_proven':False,'30_day_exact_RTH_volume_proven':False,
            'trade_correction_lineage_proven':False,'non_display_automation_rights_proven':False,
            'canonical_history_pass_authority':False,'canonical_price_pass_authority':False,
            'mc_authority':False,'g9_authority':False,'r92_count':0,'iphone_receipt_attested':False,
            'unknown_never_pass':True,'execution':'NONE','real_money':'NO-GO','broker':False,
            'canonical_files_mutated':False,'raw_vendor_bars_persisted':False,
            'secrets_persisted':False}

def api(expected,asof,key,secret):
    need(key and secret,'CREDENTIALS_UNAVAILABLE')
    start=expected[0]+'T00:00:00-04:00'
    # Last day at 16:01 America/New_York; never request a future next-midnight bound.
    end=dt.datetime.combine(dt.date.fromisoformat(asof),dt.time(16,1),NY)
    now=dt.datetime.now(UTC)
    need(end.astimezone(UTC)<=now-dt.timedelta(minutes=15),'HISTORICAL_DELAY_WINDOW')
    params={'symbols':','.join(SYMBOLS),'timeframe':'1Day','start':start,
            'end':end.isoformat(),'feed':'sip','adjustment':'raw','asof':asof,'limit':1000}
    rows={s:[] for s in SYMBOLS};token=None;used=set()
    for page in range(MAX_PAGES):
        q=dict(params)
        if token:q['page_token']=token
        url='https://data.alpaca.markets/v2/stocks/bars?'+urllib.parse.urlencode(q)
        request=urllib.request.Request(url,headers={'APCA-API-KEY-ID':key,
           'APCA-API-SECRET-KEY':secret,'Accept':'application/json',
           'User-Agent':'xray-v33-two-symbol-260-research/1.0'})
        with urllib.request.urlopen(request,timeout=22) as resp:
            raw=resp.read(MAX_BODY+1)
        need(len(raw)<=MAX_BODY,'RESPONSE_TOO_LARGE')
        obj=json.loads(raw)
        need(type(obj) is dict and type(obj.get('bars')) is dict and
             set(obj['bars']).issubset(SYMBOLS),'RESPONSE_SCOPE_INVALID')
        for symbol,chunk in obj['bars'].items():
            need(type(chunk) is list,'BARS_NOT_LIST')
            rows[symbol].extend(chunk)
        nxt=obj.get('next_page_token')
        need(nxt is None or (type(nxt) is str and 1<=len(nxt)<=2048 and nxt not in used),'PAGINATION_CURSOR')
        if nxt is None:return rows,page+1
        token=nxt;used.add(nxt)
    raise Blocked('XRAY_V33_PAGE_BUDGET_EXHAUSTED')

def selftest():
    start=dt.date(2025,10,10)
    days=[(start+dt.timedelta(days=i)).isoformat() for i in range(260)]
    def bar(d):
        midnight=dt.datetime.combine(dt.date.fromisoformat(d),dt.time(0,0),NY)
        return {'t':midnight.astimezone(UTC).isoformat(),'o':10,'h':11,'l':9,'c':10.5,'v':1000}
    good={s:[bar(d) for d in days] for s in SYMBOLS}
    weeks=days[-52:]
    positive=summarize(days,good,weeks)
    need(all(positive[s]['research_exact260_present'] and
             positive[s]['research_52_completed_weeks_present'] for s in SYMBOLS),
         'POSITIVE_260_52')
    cases=[lambda z:z['CCC'].pop(),lambda z:z['FISV'].append(dict(z['FISV'][-1])),
       lambda z:z['CCC'][10].update(v=0),lambda z:z['CCC'][10].update(v=10.2),
       lambda z:z['FISV'][5].update(h=8),lambda z:z['FISV'][5].update(l=12),
       lambda z:z['CCC'][2].update(t='2026-01-01T00:00:00'),
       lambda z:z['CCC'][2].update(o=float('nan'))]
    import copy
    for f in cases:
        x=copy.deepcopy(good);f(x)
        try:res=summarize(days,x,weeks)
        except Blocked:continue
        need(not all(res[s]['research_exact260_present'] for s in SYMBOLS),'NEGATIVE_ACCEPTED')
    safe=report('2026-10-22',positive,'RESEARCH_ONLY')
    need(not any(safe[x] for x in ('canonical_history_pass_authority','canonical_price_pass_authority',
      'mc_authority','g9_authority','raw_vendor_bars_persisted','secrets_persisted')),'NO_AUTHORITY')
    print('XRAY_V33_TWO_SYMBOL_260_SELFTEST=PASS_1_POSITIVE_8_NEGATIVE_NO_AUTHORITY')

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--selftest',action='store_true');ap.add_argument('--out',type=Path);a=ap.parse_args()
    if a.selftest:return selftest()
    if a.out is None:ap.error('--out required')
    asof='UNKNOWN';out=None
    try:
        root=json.loads((ROOT/'orchestrator_state.json').read_text())
        master=json.loads((ROOT/'canonical_current_master_manifest.json').read_text())
        asof=root['asof_et']
        need(asof==master.get('asof_et'),'ROOT_MASTER_ASOF')
        # Only do tiny provider research for FISV and CCC actually pending.
        tech=root.get('candidate_technical_funnel',{})
        need(set(tech.get('pending_symbols',[]))==set(SYMBOLS) and
            all(tech.get('results',{}).get(s,{}).get('status')=='UNKNOWN_260_OFFICIAL_HISTORY' for s in SYMBOLS),
            'ACTUAL_PENDING_SCOPE_CHANGED')
        from current_history_source_request import expected_dates
        expected,weeks=expected_dates(asof)
        need(len(expected)==260 and expected[-1]==asof and len(weeks)==52
             and set(weeks).issubset(expected),'OFFICIAL_260_52_CALENDAR_MISSING')
        key=os.getenv('XRAY_ALPACA_DATA_KEY_ID') or os.getenv('XRAY_ALPACA_API_KEY_ID') or ''
        secret=os.getenv('XRAY_ALPACA_DATA_SECRET_KEY') or os.getenv('XRAY_ALPACA_API_SECRET_KEY') or ''
        rows,pages=api(expected,asof,key,secret)
        result=summarize(expected,rows,weeks)
        status=('RESEARCH_EXACT260_52W_BOTH_PRESENT_NOT_PRIMARY' if all(
             result[s]['research_exact260_present'] and
             result[s]['research_52_completed_weeks_present'] for s in SYMBOLS)
             else 'UNKNOWN_RESEARCH_260_INCOMPLETE')
        out=report(asof,result,status,pages)
    except urllib.error.HTTPError as e:
        out=report(asof,status=('BLOCKED_HTTP_401' if e.code==401 else
          'BLOCKED_HTTP_403_POLICY_OR_WINDOW' if e.code==403 else
          'BLOCKED_HTTP_429_RATE_LIMIT' if e.code==429 else 'BLOCKED_HTTP_OTHER'))
    except (Blocked,ValueError,KeyError,TypeError,TimeoutError,urllib.error.URLError,OSError):
        out=report(asof,status='BLOCKED_SOURCE_OR_SCOPE_UNVERIFIED')
    need(out['canonical_history_pass_authority'] is False and out['r92_count']==0,'NO_FALSE_AUTHORITY')
    a.out.write_text(json.dumps(out,sort_keys=True,indent=2)+'\n')
    print('XRAY_V33_260_COUNTS_ONLY='+json.dumps({'status':out['status'],'asof_et':out['asof_et'],
     'sip_pages_used':out['sip_pages_used'],'symbol_counts':out['symbol_counts']},sort_keys=True))

if __name__=='__main__':main()