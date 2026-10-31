#!/usr/bin/env python3
"""XRAY NASDAQ OFFLINE official-source research contract.

No HTTP, credentials, GitHub writes, Sheets, broker, AL, alerts or orders.
Responses supplied by an external authorized collector are untrusted fixtures;
passing shape checks does NOT prove their origin, completeness, or point-in-time
availability. ALL conclusions remain RESEARCH_ONLY / fail-closed.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import json
import re
from xml.etree import ElementTree as ET

SCHEMA = 'XRAY_NASDAQ_OFFICIAL_RISK_SHADOW_V1'
SYMBOL = re.compile(r'^[A-Z][A-Z0-9.]{0,14}$')
ACCESSION = re.compile(r'^\d{10}-\d{2}-\d{6}$')
RISKS = frozenset(('8-K','8-K/A','10-Q','10-Q/A','10-K','10-K/A','4','4/A','6-K','20-F'))
ALPACA_KINDS = frozenset(('reverse_split','forward_split','unit_split','cash_dividend',
    'stock_dividend','spin_off','cash_merger','stock_merger','stock_and_cash_merger',
    'redemption','name_change','worthless_removal','rights_distribution',
    'partial_call','reorganization','capital_gains_distribution'))

class SourceRefused(ValueError):
    pass

def require(condition: bool, reason: str):
    if not condition:
        raise SourceRefused(reason)

def instant(s: str) -> datetime:
    require(type(s) is str and len(s) <= 40, 'TIMESTAMP_MISSING')
    try:
        t = datetime.fromisoformat(s.replace('Z', '+00:00'))
    except ValueError as exc:
        raise SourceRefused('TIMESTAMP_INVALID') from exc
    require(t.tzinfo is not None, 'TIMESTAMP_NAIVE')
    return t.astimezone(timezone.utc)

def day(s: str) -> date:
    require(type(s) is str and len(s) == 10, 'DATE_INVALID')
    try:
        d = date.fromisoformat(s)
    except ValueError as exc:
        raise SourceRefused('DATE_INVALID') from exc
    require(d.isoformat() == s, 'DATE_NONCANONICAL')
    return d

def symbol(s: str):
    require(type(s) is str and SYMBOL.fullmatch(s) is not None, 'SYMBOL_INVALID')
    return s

def base(source: str, ticker: str, *, asof_utc: str, observed_at_utc: str):
    symbol(ticker)
    end, seen = instant(asof_utc), instant(observed_at_utc)
    require(seen <= end, 'SOURCE_OBSERVED_AFTER_CUTOFF')
    return {'schema':SCHEMA, 'source':source, 'symbol':ticker,
            'observed_at_utc':seen.isoformat(), 'cutoff_utc':end.isoformat(),
            'research_only':True, 'source_origin_independently_attested':False,
            'history_complete_proven':False, 'pit_available_proven':False,
            'may_issue_al':False, 'may_modify_stop_or_target':False,
            'may_send_alert':False, 'may_write_sheet':False, 'may_place_order':False}

def inspect_sec(submissions: dict, cik: str, ticker: str, *, asof_utc: str,
                observed_at_utc: str):
    out=base('SEC_EDGAR_SUBMISSIONS',ticker,asof_utc=asof_utc,observed_at_utc=observed_at_utc)
    require(type(cik) is str and re.fullmatch(r'\d{10}',cik), 'CIK_INVALID')
    # SEC EDGAR submissions JSON serializes 'cik' as decimal TEXT (for example,
    # "0001718227"), although some older synthetic fixtures used an integer.
    # Never accept bool, float, whitespace, scientific notation or a mismatched
    # CIK merely because the JSON has the expected ROAD ticker.
    declared_cik = submissions.get('cik') if type(submissions) is dict else None
    cik_matches = (
        (type(declared_cik) is int and declared_cik == int(cik)) or
        (type(declared_cik) is str and
         re.fullmatch(r'[0-9]{1,10}', declared_cik) is not None and
         int(declared_cik) == int(cik))
    )
    require(cik_matches, 'SEC_ISSUER_CIK_MISMATCH')
    tickers=submissions.get('tickers')
    require(type(tickers) is list and ticker in tickers and
            all(type(x) is str for x in tickers), 'SEC_CURRENT_TICKER_MISMATCH')
    # SEC's tickers describe the CURRENT snapshot, not historic listing/PIT.
    recent=submissions.get('filings',{}).get('recent')
    require(type(recent) is dict, 'SEC_RECENT_NOT_COLUMNAR')
    fields=('accessionNumber','form','filingDate','acceptanceDateTime')
    columns=[recent.get(k) for k in fields]
    require(all(type(x) is list for x in columns),'SEC_RECENT_MISSING_COLUMNS')
    # SEC's "at least one year or 1000, whichever is MORE" contract permits
    # legitimate submissions above 1000 rows. Limit memory defensively,
    # never confuse a safety bound with official completeness.
    n=len(columns[0]);require(n<=20000 and all(len(x)==n for x in columns),
                        'SEC_COLUMN_LENGTH_DRIFT')
    seen_ids=set();events=[];disputed=[];seen=instant(observed_at_utc);cutoff=instant(asof_utc)
    for acc,form,filing,accepted in zip(*columns):
        require(type(acc) is str and ACCESSION.fullmatch(acc) and acc not in seen_ids,
                'SEC_ACCESSION_DUPLICATE_OR_INVALID')
        seen_ids.add(acc)
        day(filing)
        require(type(form) is str and form, 'SEC_FORM_INVALID')
        a=instant(accepted)
        # This uncorroborated submissions timestamp MUST NOT silently erase
        # a relevant filing. Quarantine it without asserting PIT availability.
        if a > seen or a > cutoff:
            if form in RISKS:
                disputed.append({'event_id':cik+'|'+acc, 'form':form,
                                 'filing_date':filing,
                                 'reported_acceptance_utc':a.isoformat(),
                                 'classification':'TIMESTAMP_DISPUTE_REVIEW_ONLY'})
            continue
        if form in RISKS:
            events.append({'event_id':cik+'|'+acc, 'form':form,
                           'filing_date':filing, 'accepted_utc':a.isoformat(),
                           'classification':'OFFICIAL_FILING_REVIEW_ONLY'})
    supplemental=submissions.get('filings',{}).get('files')
    supplemental_count = len(supplemental) if type(supplemental) is list else None
    return {**out,'status':('SEC_TIMESTAMP_DISPUTE_REVIEW_REQUIRED' if disputed
                            else 'SEC_EVENTS_REVIEW' if events
                            else 'SEC_NO_EVENT_NOT_CLEAR'),
            'current_ticker_identity_only':True,
            'acceptance_not_publication_timestamp':True,
            'acceptance_utc_independently_crosschecked':False,
            'recent_filing_rows_observed':n,
            'supplemental_history_files_declared':supplemental_count,
            'filing_history_exhaustiveness_proven':False,
            'timestamp_dispute_count':len(disputed),
            'timestamp_dispute_events':disputed,
            'timestamp_dispute_may_prove_late_publication':False,
            'events':events,'event_count':len(events)}

def _local(tag):
    return tag.split('}',1)[-1].lower()

def _xml_text(item, *names):
    accepted={n.lower() for n in names}
    vals=[(n.text or '').strip() for n in item if _local(n.tag) in accepted]
    require(len(vals)<=1, 'RSS_AMBIGUOUS_FIELD')
    return vals[0] if vals else ''

def inspect_nasdaq_halts(xml: str, ticker: str, *, asof_utc: str,
                         observed_at_utc: str):
    out=base('NASDAQ_TRADER_HALT_RSS',ticker,asof_utc=asof_utc,observed_at_utc=observed_at_utc)
    require(type(xml) is str and 0<len(xml.encode('utf-8'))<=2_000_000,
            'RSS_SIZE_BOUNDS')
    require('<!DOCTYPE' not in xml.upper() and '<!ENTITY' not in xml.upper(),
            'RSS_DTD_ENTITY_FORBIDDEN')
    try: root=ET.fromstring(xml)
    except ET.ParseError as exc: raise SourceRefused('RSS_MALFORMED') from exc
    require(_local(root.tag)=='rss' and root.find('channel') is not None,
            'RSS_ROOT_NOT_CHANNEL')
    items=list(root.find('channel').findall('item'))
    require(len(items)<=1000,'RSS_TOO_MANY_ITEMS')
    events=[];ids=set();seen=instant(observed_at_utc)
    for it in items:
        s=_xml_text(it,'symbol','issuesymbol','issue_symbol')
        if not s:
            raise SourceRefused('RSS_MISSING_EXPLICIT_SYMBOL')
        symbol(s)
        hdate=_xml_text(it,'haltdate','halt_date')
        htime=_xml_text(it,'halttime','halt_time')
        code=_xml_text(it,'reasoncode','reason_code')
        require(bool(code) and bool(htime) and bool(hdate), 'RSS_HALT_DETAILS_MISSING')
        try:
            if re.fullmatch(r'\d{2}/\d{2}/\d{4}',hdate):
                d=datetime.strptime(hdate,'%m/%d/%Y').date()
            else:d=day(hdate)
        except ValueError as exc:raise SourceRefused('RSS_HALT_DATE_INVALID') from exc
        require(re.fullmatch(r'\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?',htime),
                'RSS_HALT_TIME_INVALID')
        # Time-of-day in ET is not proof of public feed availability.
        require(d<=seen.date(), 'RSS_FUTURE_HALT_DATE')
        key=f'{s}|{d.isoformat()}|{htime}|{code}'
        require(key not in ids,'RSS_DUPLICATE_EVENT')
        ids.add(key)
        if s==ticker:
            events.append({'event_id':key,'reason_code':code,
                           'halt_date':d.isoformat(),'halt_time_et':htime,
                           'classification':'HALT_OR_RESUMPTION_REVIEW_ONLY'})
    return {**out,'status':'NASDAQ_HALT_REVIEW' if events else 'NASDAQ_NO_ITEM_NOT_CLEAR',
            'feed_refresh_does_not_guarantee_delivery':True,
            'resumption_not_confirmed_by_parser':True, 'events':events,
            'event_count':len(events)}

def inspect_alpaca_actions(api: dict, ticker: str, *, asof_utc: str,
                           observed_at_utc: str):
    out=base('ALPACA_CORPORATE_ACTIONS',ticker,asof_utc=asof_utc,observed_at_utc=observed_at_utc)
    require(type(api) is dict and type(api.get('corporate_actions')) is list,
            'CA_RESPONSE_MISSING')
    require(api.get('next_page_token') in ('',None), 'CA_PAGINATION_INCOMPLETE')
    acts=api['corporate_actions'];require(len(acts)<=1000, 'CA_LIMIT_EXCEEDED')
    ids=set();events=[];end=instant(asof_utc)
    for x in acts:
        require(type(x) is dict,'CA_MALFORMED')
        ident=x.get('id');kind=x.get('type');sym=x.get('symbol')
        require(type(ident) is str and 0<len(ident)<=100 and ident not in ids,
                'CA_DUPLICATE_OR_MISSING_ID')
        ids.add(ident)
        require(type(kind) is str and kind in ALPACA_KINDS, 'CA_UNKNOWN_KIND')
        require(type(sym) is str and symbol(sym)==sym,'CA_SYMBOL_INVALID')
        process=day(x.get('process_date'))
        if process>end.date():
            continue  # no use of future-dated events in current risk conclusion
        if sym==ticker:
            events.append({'event_id':ident,'kind':kind,'process_date':process.isoformat(),
                           'classification':'CORPORATE_ACTION_REVIEW_NO_PRICE_ADJUSTMENT'})
    return {**out,'status':'CORPORATE_ACTION_REVIEW' if events else 'CA_NONE_NOT_CLEAR',
            'provider_creation_latency_unbounded':True,
            'adjusted_price_or_volume_generated':False,'events':events,
            'event_count':len(events)}

def inspect_nasdaq_directory(content: str, ticker: str, *, asof_utc: str,
                             observed_at_utc: str):
    out=base('NASDAQ_TRADER_SYMBOL_DIRECTORY',ticker,asof_utc=asof_utc,observed_at_utc=observed_at_utc)
    require(type(content) is str and 0<len(content)<=2_000_000, 'DIR_SIZE_BOUNDS')
    lines=[x.strip() for x in content.splitlines() if x.strip()]
    require(2<=len(lines)<=20000,'DIR_LINE_BOUNDS')
    header=lines[0].split('|')
    required=('Symbol','Security Name','Market Category','Test Issue','Financial Status','ETF')
    require(all(h in header for h in required) and len(header)==len(set(header)),
            'DIR_HEADER_DRIFT')
    require(lines[-1].startswith('File Creation Time:'),'DIR_CREATION_TIMESTAMP_MISSING')
    token=lines[-1].split('|',1)[0].removeprefix('File Creation Time:').strip()
    require(re.fullmatch(r'\d{12}|\d{8}\d{2}:\d{2}',token) is not None,
            'DIR_CREATION_TIMESTAMP_INVALID')
    try:when=datetime.strptime(token.replace(':',''),'%m%d%Y%H%M')
    except ValueError as exc:raise SourceRefused('DIR_CREATION_TIMESTAMP_INVALID') from exc
    # A local ET timestamp is only comparable by its DATE. It is not PIT history.
    require(when.date()<=instant(observed_at_utc).date(),
            'DIR_CREATED_AFTER_OBSERVATION')
    positions={v:i for i,v in enumerate(header)}
    entries={}
    for l in lines[1:-1]:
        cols=l.split('|');require(len(cols)==len(header),'DIR_COLUMN_DRIFT')
        sym=cols[positions['Symbol']];symbol(sym)
        require(sym not in entries,'DIR_DUPLICATE_TICKER')
        entries[sym]=cols
    row=entries.get(ticker)
    if row is None:
        status='DIRECTORY_SYMBOL_NOT_FOUND_REVIEW'
    elif row[positions['Test Issue']]!='N' or row[positions['ETF']]!='N' or row[positions['Financial Status']]!='N':
        status='DIRECTORY_STATUS_REVIEW'
    else:status='DIRECTORY_CURRENT_MATCH_REVIEW_ONLY'
    return {**out,'status':status,'snapshot_creation_local_et':token,
            'historical_membership_not_proven':True,
            'current_record_count':len(entries),'symbol_found':row is not None}

def offline_summary(ticker:str, *, asof_utc: str, observed_at_utc: str,
                    sec=None,halts=None,corporate_actions=None,directory=None,cik=None):
    symbol(ticker)
    collectors=(('SEC_EDGAR',lambda:inspect_sec(sec,cik,ticker,asof_utc=asof_utc,observed_at_utc=observed_at_utc),sec),
     ('NASDAQ_HALTS',lambda:inspect_nasdaq_halts(halts,ticker,asof_utc=asof_utc,observed_at_utc=observed_at_utc),halts),
     ('ALPACA_CORPORATE_ACTIONS',lambda:inspect_alpaca_actions(corporate_actions,ticker,asof_utc=asof_utc,observed_at_utc=observed_at_utc),corporate_actions),
     ('NASDAQ_DIRECTORY',lambda:inspect_nasdaq_directory(directory,ticker,asof_utc=asof_utc,observed_at_utc=observed_at_utc),directory))
    sources={}
    for name,fn,payload in collectors:
        if payload is None:
            sources[name]={'status':'NOT_PROVIDED_NOT_CLEAR'}
        else:
            try:sources[name]=fn()
            except (SourceRefused,TypeError,KeyError,AttributeError) as e:
                sources[name]={'status':'SOURCE_REFUSED','reason':str(e) if isinstance(e,SourceRefused) else type(e).__name__}
    return {'schema':SCHEMA,'ticker':ticker,'state':'RESEARCH_REVIEW_ONLY_NO_CLEARANCE',
            'sources':sources,'may_modify_al':False,'may_emit_alert':False,
            'may_place_order':False,'may_write_sheet':False,
            'market_event_exhaustiveness_proven':False}

if __name__=='__main__':
    # Always offline, no automatic web or broker activity.
    print(json.dumps(offline_summary('AAPL',asof_utc='2026-10-31T04:00:00Z',
         observed_at_utc='2026-10-31T03:00:00Z'),sort_keys=True))