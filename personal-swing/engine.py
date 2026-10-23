#!/usr/bin/env python3
"""XRAY START/FINAL: personal NASDAQ IEX daily swing screening. NO broker, NO orders.

Example immediate run:
    python xray_personal_start_final.py --input START_FINAL_2026-10-22.json

New screening, with the user's own existing Alpaca DATA credentials:
    ALPACA_API_KEY_ID=... ALPACA_API_SECRET_KEY=... \
      python xray_personal_start_final.py --refresh --repo-watchlist --out today.json

IEX is one exchange, not total U.S. consolidated volume. Not financial advice.
Refresh requires an official NASDAQ calendar; stale dates fail closed.
"""
import argparse
import datetime as dt
import json
import math
import os
from pathlib import Path
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

REPO_DIGEST="https://raw.githubusercontent.com/gokaydonmez39-jpg/kripto-radar/main/nasdaq-xray/personal_research_signal_digest.json"
DEFAULT_SYMBOLS="ADI COKE CTSH CVLT DOCU HTFL ISRG MANH MKTX MRNA PLTR QLYS TENB VRNS WAY WDAY WIX XP NVDA MU META AAPL MSFT AMZN GOOGL TSLA AMD AVGO NFLX COST".split()
SCHEMA="XRAY_PERSONAL_START_FINAL_V1"


def mean(vals):
    return sum(vals)/len(vals)


def trading_asof(now=None):
    """Latest COMPLETED official XNAS session, allowing 45 minutes for EOD bars.

    This is an equity-session calculation, not a weekday subtraction.
    For production auto-refresh install exchange_calendars (see requirements.txt).
    """
    try:
        import exchange_calendars as ec
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError('Install calendar dependency: pip install -r requirements.txt') from exc
    instant=(now or dt.datetime.now(dt.timezone.utc))
    if instant.tzinfo is None:
        raise ValueError('Current time must include a timezone')
    instant=instant.astimezone(dt.timezone.utc)
    calendar=ec.get_calendar('XNAS')
    start=(instant-dt.timedelta(days=15)).date().isoformat()
    end=(instant+dt.timedelta(days=1)).date().isoformat()
    sessions=calendar.sessions_in_range(start,end)
    completed=[session.date() for session in sessions
               if calendar.session_close(session).to_pydatetime() + dt.timedelta(minutes=45) <= instant]
    if not completed:
        raise RuntimeError('No completed Nasdaq session found within 15 days')
    return completed[-1]


def validate_asof(asof):
    """Reject weekends/holidays and future or unfinished explicit dates."""
    try:
        import exchange_calendars as ec
    except ImportError as exc:
        raise RuntimeError('Install calendar dependency: pip install -r requirements.txt') from exc
    selected=dt.date.fromisoformat(asof)
    if not ec.get_calendar('XNAS').is_session(selected.isoformat()):
        raise ValueError('Requested asof is not a NASDAQ trading session')
    if selected > trading_asof():
        raise ValueError('Requested asof session is not yet completed')
    return selected


def analyze(symbol, bars, asof):
    """Deterministic raw single-exchange IEX daily screen. Never trade or call a broker."""
    observations={}
    for x in bars:
        day=str(x.get('timestamp',''))[:10]
        if not day or day>asof:
            continue
        if day in observations:
            raise ValueError('Duplicate daily bar: '+symbol+' '+day)
        vals=[x.get(k) for k in ('open','high','low','close','volume')]
        if any(type(v) not in (int,float) or not math.isfinite(v) or v<=0 for v in vals):
            raise ValueError('Invalid OHLCV: '+symbol+' '+day)
        if x['low']>x['high'] or not x['low']<=x['open']<=x['high'] or not x['low']<=x['close']<=x['high']:
            raise ValueError('Invalid OHLC range: '+symbol+' '+day)
        observations[day]=x
    ordered=[observations[k] for k in sorted(observations)]
    # An old bar must NEVER be presented as a fresh decision for a new ASOF.
    if not ordered or ordered[-1]['timestamp'][:10] != asof:
        return {'symbol':symbol,'sessions':len(ordered),'asof_et':asof,
                'decision':'VERI_YETERSIZ','reasons':['MISSING_EXACT_ASOF_BAR']}
    if len(ordered)<52:
        return {'symbol':symbol,'sessions':len(ordered),'asof_et':asof,'decision':'VERI_YETERSIZ','reasons':['Insufficient IEX daily history']}
    # Last 52 daily observations must cover 52 successive official XNAS sessions.
    # Gaps are not interchangeable with a 52-bar calendar sample, especially
    # around holidays / early closes. Do not produce an AL from incomplete history.
    import exchange_calendars as ec
    cal=ec.get_calendar('XNAS')
    recent_days=list(sorted(observations))[-52:]
    expected=[str(t.date()) for t in cal.sessions_in_range(recent_days[0],asof)]
    if recent_days!=expected:
        return {'symbol':symbol,'sessions':len(ordered),'asof_et':asof,
                'decision':'VERI_YETERSIZ','reasons':['NONCONTIGUOUS_52_OFFICIAL_XNAS_SESSIONS']}
    b=ordered[-1]; prior=ordered[:-1]; closes=[x['close'] for x in ordered]
    ma20=mean(closes[-20:]);ma50=mean(closes[-50:]);hi20=max(x['high'] for x in prior[-20:]);volume20=mean([x['volume'] for x in prior[-20:]])
    relative=b['volume']/volume20
    gains=losses=0.0
    for i in range(len(ordered)-14,len(ordered)):
        delta=closes[i]-closes[i-1]
        gains+=max(delta,0); losses+=max(-delta,0)
    rsi=100 if losses==0 else 100-100/(1+gains/losses)
    true_ranges=[]
    for i in range(len(ordered)-14,len(ordered)):
        x,pr=ordered[i],ordered[i-1]
        true_ranges.append(max(x['high']-x['low'],abs(x['high']-pr['close']),abs(x['low']-pr['close'])))
    atr=mean(true_ranges)
    price=b['close']; stop=price-2*atr; risk=2*atr/price
    trend=price>ma20>ma50; breakout=price>hi20
    liquid=price*volume20>=500000
    failures=[]
    if price<5: failures.append('FIYAT_LT5')
    if not trend: failures.append('TREND_YETERSIZ')
    if not breakout: failures.append('KIRILIM_YOK')
    if relative<1.3: failures.append('IEX_REL_VOL_LT1_3')
    if not 45<=rsi<=75: failures.append('RSI_DISINDA')
    if risk>0.08: failures.append('STOP_RISK_GT8')
    if not liquid: failures.append('IEX_LIKIDITE_DUSUK')
    buy=not failures
    dist=(hi20-price)/hi20
    watch=not buy and trend and -0.05<=dist<=0.04 and price>=5 and liquid
    return {'symbol':symbol,'sessions':len(ordered),'asof_et':ordered[-1]['timestamp'][:10],
            'close':round(price,3),'sma20':round(ma20,3),'sma50':round(ma50,3),
            'prior_high20':round(hi20,3),'relative_iex_volume':round(relative,3),'rsi14':round(rsi,2),
            'atr14':round(atr,3),'atr_risk_pct':round(risk*100,2),
            'indicative_stop':round(stop,3),'indicative_target_2r':round(price+2*(price-stop),3),
            'distance_to_breakout_pct':round(dist*100,2),'decision':'AL' if buy else ('IZLE' if watch else 'ELE'),
            'reasons':failures,'source':'ALPACA_IEX_DAILY'}


def get_json(url,headers=None,retries=2):
    for i in range(retries+1):
        try:
            req=urllib.request.Request(url,headers=headers or {'User-Agent':'XRAY-personal-readonly-v1'})
            with urllib.request.urlopen(req,timeout=30) as res:
                return json.load(res)
        except urllib.error.HTTPError as exc:
            if exc.code not in (429,500,502,503,504) or i==retries:
                raise
            time.sleep(1+i*2)
    raise RuntimeError('Unexpected empty fetch')


def read_watchlist(repo=False,symbols=None):
    if symbols:
        return list(dict.fromkeys(x.strip().upper() for x in symbols.split(',') if x.strip()))
    if repo:
        data=get_json(REPO_DIGEST)
        xs=data.get('liquidity_watch_symbols') or []
        if not isinstance(xs,list) or not xs:
            raise ValueError('Repository watchlist missing')
        return list(dict.fromkeys(str(x).strip().upper() for x in xs))
    return DEFAULT_SYMBOLS[:]


def normalize_alpaca_raw_bar(raw, symbol):
    """Translate Alpaca REST bars (t/o/h/l/c/v) to analysis schema.

    Never synthesize missing fields, silently coerce strings or use other feeds.
    Volume is IEX-only, NOT SIP-consolidated. Source timestamps must be ISO-8601.
    """
    if not isinstance(raw,dict):
        raise ValueError('ALPACA_BAR_NOT_DICT_'+symbol)
    names={'timestamp':'t','open':'o','high':'h','low':'l','close':'c','volume':'v'}
    clean={}
    for target,source in names.items():
        v=raw.get(source,raw.get(target))
        if v is None:
            raise ValueError('ALPACA_MISSING_'+target+'_'+symbol)
        clean[target]=v
    # Validate fields now rather than allowing bad OHLCV to be misclassified.
    import math
    try:
        from datetime import datetime
        date=datetime.fromisoformat(str(clean['timestamp']).replace('Z','+00:00'))
    except (ValueError,TypeError) as exc:
        raise ValueError('ALPACA_INVALID_TIMESTAMP_'+symbol) from exc
    if date.tzinfo is None:raise ValueError('ALPACA_TIMESTAMP_WITHOUT_TZ_'+symbol)
    clean['timestamp']=date.isoformat()
    for f in ['open','high','low','close','volume']:
        value=clean[f]
        if type(value) not in (int,float) or not math.isfinite(value) or value<=0:
            raise ValueError('ALPACA_INVALID_'+f+'_'+symbol)
    if clean['low']>min(clean['open'],clean['close']) or clean['high']<max(clean['open'],clean['close']):
        raise ValueError('ALPACA_BAD_RANGE_'+symbol)
    return clean


def live_read(symbols,asof):
    """Read-only Alpaca IEX REST transport; validated pagination and raw-bar mapping.

    No broker, trading, account or order endpoints are invoked.
    """
    key=os.getenv('XRAY_ALPACA_DATA_KEY_ID') or os.getenv('ALPACA_API_KEY_ID') or os.getenv('APCA_API_KEY_ID')
    secret=os.getenv('XRAY_ALPACA_DATA_SECRET_KEY') or os.getenv('ALPACA_API_SECRET_KEY') or os.getenv('APCA_API_SECRET_KEY')
    if not key or not secret:
        raise PermissionError('MISSING_PERSONAL_DATA_ONLY_API_KEYS')
    if not symbols or len(set(symbols))!=len(symbols) or any(not isinstance(s,str) or not s.isascii() or s.upper()!=s for s in symbols):
        raise ValueError('INVALID_EXACT_SYMBOL_SET')
    headers={'APCA-API-KEY-ID':key,'APCA-API-SECRET-KEY':secret,'User-Agent':'XRAY-personal-readonly-v6'}
    target=dt.date.fromisoformat(asof)
    start=target-dt.timedelta(days=155)
    stop=target+dt.timedelta(days=1)
    et=ZoneInfo('America/New_York')
    start_et=dt.datetime.combine(start,dt.time.min,tzinfo=et).isoformat()
    stop_et=dt.datetime.combine(stop,dt.time.min,tzinfo=et).isoformat()
    result={sym:[] for sym in symbols}
    for k in range(0,len(symbols),10):
        group=symbols[k:k+10]
        token=None
        seen_tokens=set()
        for page in range(50):
            args={'symbols':','.join(group),'timeframe':'1Day','start':start_et,
                  'end':stop_et,'adjustment':'raw','feed':'iex','sort':'asc','limit':10000}
            if token:args['page_token']=token
            endpoint='https://data.alpaca.markets/v2/stocks/bars?'+urllib.parse.urlencode(args)
            d=get_json(endpoint,headers=headers)
            if not isinstance(d,dict) or not isinstance(d.get('bars'),dict):
                raise ValueError('ALPACA_INVALID_RESPONSE_SCHEMA')
            for sym,observations in d['bars'].items():
                if sym not in result or sym not in group:
                    raise ValueError('ALPACA_UNREQUESTED_SYMBOL')
                if not isinstance(observations,list):raise ValueError('ALPACA_BARS_NOT_LIST_'+sym)
                result[sym].extend(normalize_alpaca_raw_bar(row,sym) for row in observations)
            next_token=d.get('next_page_token')
            if not next_token:break
            if not isinstance(next_token,str) or next_token in seen_tokens:
                raise ValueError('ALPACA_REPEATED_OR_INVALID_PAGE_TOKEN')
            seen_tokens.add(next_token)
            token=next_token
        else:raise RuntimeError('ALPACA_PAGINATION_OVER_50_PAGES')
    return result

def assemble(rows,asof,scope):
    sortkey={'AL':0,'IZLE':1,'ELE':2,'VERI_YETERSIZ':3}
    rows.sort(key=lambda x:(sortkey.get(x['decision'],4),-x.get('relative_iex_volume',0),x['symbol']))
    counts={'START':len(rows),'TEKNIK_AL_ADAYI':sum(r['decision']=='AL' for r in rows),
            'YAKIN_IZLE':sum(r['decision']=='IZLE' for r in rows),'ELE':sum(r['decision']=='ELE' for r in rows),
            'VERI_YETERSIZ':sum(r['decision']=='VERI_YETERSIZ' for r in rows)}
    return {'schema':SCHEMA,'asof_et':asof,'feed':'ALPACA_IEX_DAILY_ONE_EXCHANGE',
        'source_limitations':'IEX ONLY; one exchange, NOT consolidated NASDAQ / SIP. No broker or orders.',
        'scope':scope,'counts':counts,'rows':rows,'not_broker':True,'orders_sent':0,'auto_trading':False}


def show(snap,kind):
    c=snap['counts']; print('XRAY PERSONAL',kind,'| ET seans:',snap['asof_et'],'| Veri:',snap['feed'])
    print('START:',c['START'],'FINAL AL:',c['TEKNIK_AL_ADAYI'],'IZLE:',c['YAKIN_IZLE'],'ELE:',c['ELE'],'VERI_EKSIK:',c['VERI_YETERSIZ'])
    print('Bu yalnızca kişisel teknik araştırma radaridir; broker / emir / otomatik işlem YOK.')
    for x in snap['rows']:
        if kind=='FINAL' and x['decision'] not in ('AL','IZLE'):continue
        print(f"{x['symbol']:7} {x['decision']:14} ${x.get('close',0):>8.2f} RV {x.get('relative_iex_volume',0):>4.2f} RSI {x.get('rsi14',0):>5.1f} risk% {x.get('atr_risk_pct',0):>5.1f}")


def main(argv=None):
    ap=argparse.ArgumentParser(description='Only personal EOD IEX swing signal radar; no broker, no orders')
    mode=ap.add_mutually_exclusive_group(required=True)
    mode.add_argument('--input',help='previous START_FINAL JSON snapshot')
    mode.add_argument('--refresh',action='store_true',help='read own Alpaca IEX historical bars and recalculate')
    ap.add_argument('--repo-watchlist',action='store_true',help='use existing repository 477-watchlist source (may consume provider quota)')
    ap.add_argument('--symbols',help='comma separated tickers; default 30 symbols')
    ap.add_argument('--asof',help='latest completed ET day YYYY-MM-DD; default auto ET date')
    ap.add_argument('--out',help='output JSON path (only refresh mode)')
    ap.add_argument('--final',action='store_true',help='print FINAL only (otherwise START and FINAL)')
    args=ap.parse_args(argv)
    if args.input:
        snap=json.loads(Path(args.input).read_text(encoding='utf-8'))
        if snap.get('schema')!=SCHEMA:raise ValueError('Invalid snapshot format')
        if len(snap.get('rows',[]))!=snap.get('counts',{}).get('START'):raise ValueError('Snapshot count mismatch')
    else:
        asof=args.asof or trading_asof().isoformat()
        validate_asof(asof)
        symbols=read_watchlist(args.repo_watchlist,args.symbols)
        bars=live_read(symbols,asof)
        rows=[]
        for sym in symbols:
            try:rows.append(analyze(sym,bars.get(sym,[]),asof))
            except (ValueError,KeyError,TypeError,ZeroDivisionError) as exc:
                rows.append({'symbol':sym,'asof_et':asof,'decision':'VERI_YETERSIZ','reasons':[type(exc).__name__]})
        snap=assemble(rows,asof,f'IEX live read, {len(symbols)} requested from current personal list')
        dst=Path(args.out or ('XRAY_START_FINAL_'+asof+'.json'))
        dst.write_text(json.dumps(snap,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
        print('Snapshot saved:',dst)
    if not args.final:show(snap,'START')
    show(snap,'FINAL')
    return 0


if __name__=='__main__':
    sys.exit(main())
