#!/usr/bin/env python3
"""XRAY v25: fail-closed provenance preflight for existing GitHub research chain.

RESEARCH-ONLY. Zero network, zero broker/order/market execution, zero AL.
The producer's immutable source-manifest, when provided, must be trusted through
an independently attested parent run/commit. A manifest is NOT a signature.
Never promote this check to C4.17 / G9 / R92 approval.
"""
import argparse
from datetime import date
import hashlib
import json
import re
from pathlib import Path

SHA = re.compile(r"[a-f0-9]{40}\Z")
SYMBOL = re.compile(r"[A-Z0-9.]+\Z")
DOCS = ("root", "master", "price")

class GateFailure(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)

def demand(condition, code):
    if not condition:
        raise GateFailure(code)

def git_blob(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode('ascii') + b"\0" + raw).hexdigest()

def parse_day(value):
    demand(type(value) is str and re.fullmatch(r"20\d\d-\d\d-\d\d", value) is not None,"BAD_ASOF_FORMAT")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise GateFailure("BAD_ASOF_DATE") from None

def check_source(root, master, price, actual_blobs, pinned_blobs, producer_commit=None):
    """Only the existing personal research digest's source-side policy gates.

    This intentionally does not duplicate the full numerical formula audits.
    It does not accept data merely because it has matching dates.
    """
    demand(type(actual_blobs) is dict and type(pinned_blobs) is dict
           and set(actual_blobs)==set(DOCS) and set(pinned_blobs)==set(DOCS),
           "BLOB_SET_INCOMPLETE_OR_EXTRA")
    for key in DOCS:
        demand(type(actual_blobs[key]) is str and SHA.fullmatch(actual_blobs[key]) is not None,
               "INVALID_ACTUAL_GIT_BLOB_"+key.upper())
        demand(type(pinned_blobs[key]) is str and SHA.fullmatch(pinned_blobs[key]) is not None,
               "INVALID_PINNED_GIT_BLOB_"+key.upper())
        demand(actual_blobs[key]==pinned_blobs[key],"PINNED_SOURCE_DRIFT_"+key.upper())
    if producer_commit is not None:
        demand(type(producer_commit) is str and SHA.fullmatch(producer_commit) is not None,
               "PRODUCER_COMMIT_INVALID")
    demand(all(type(x) is dict for x in (root,master,price)),"DOC_NOT_OBJECT")
    w=root.get('watch_radar'); t=root.get('candidate_technical_funnel')
    demand(type(w) is dict and type(t) is dict,"ROOT_NESTED_MISSING")
    asofs=[root.get('asof_et'),w.get('asof_et'),t.get('asof_et'),master.get('asof_et'),price.get('asof_et')]
    days=[parse_day(v) for v in asofs]
    demand(len(set(days))==1,"SAME_ASOF_MISMATCH")
    for k,v in (("ROOT",root),("WATCH",w),("TECH",t),("MASTER",master),("PRICE",price)):
        demand(v.get('execution')=='NONE' and v.get('real_money')=='NO-GO',"EXECUTION_SCOPE_"+k)
    for k,v in (("WATCH",w),("TECH",t),("MASTER",master),("PRICE",price)):
        demand(v.get('unknown_never_pass') is True,"UNKNOWN_POLICY_"+k)
    names=master.get('pass_symbols')
    demand(type(names) is list and all(type(s) is str and SYMBOL.fullmatch(s) for s in names)
           and names==sorted(set(names)) and type(master.get('pass_count')) is int
           and len(names)==master['pass_count'],"MASTER_MEMBERSHIP_BAD")
    queue=master.get('queue_hash')
    demand(type(queue) is str and re.fullmatch('[a-f0-9]{64}',queue) is not None,
           "MASTER_QUEUE_HASH_BAD")
    demand(price.get('source_master_queue_hash')==queue
           and price.get('source_master_count')==len(names),"PRICE_MASTER_LINK_BAD")
    # Source-side attestation alone cannot certify volume, history, licensing,
    # event clearance, terminal binding, registered R92 or phone delivery.
    return {'status':'SAME_ASOF_SOURCE_BINDING_RESEARCH_ONLY',
            'asof_et':asofs[0], 'source_git_blobs':dict(actual_blobs),
            'producer_commit':producer_commit,
            'execution':'NONE','real_money':'NO-GO',
            'unknown_never_pass':True,
            'market_data_verified':False,'canonical_C417_pass':False,
            'g9_pass':False,'registered_r92_count':0,
            'iphone_receipt_attested':False,'alert_authority':False}

def check_consumer_date(source, digest, overlay):
    """Optional terminal availability test. A stale digest is not a BUY failure;
    it is a blocked-publication/rebuild condition.
    """
    demand(type(digest) is dict and type(overlay) is dict,"CONSUMER_DOC_BAD")
    source_asof=parse_day(source['asof_et'])
    other=[parse_day(digest.get('asof_et')),parse_day(overlay.get('asof_et'))]
    demand(all(a==source_asof for a in other),"CONSUMER_STALE_BLOCK_PUBLICATION")
    demand(digest.get('automated_alert_authority') is False
           and digest.get('certified_C417_AL_signal_count')==0
           and digest.get('execution')=='NONE'
           and digest.get('real_money')=='NO-GO'
           and digest.get('iphone_receipt_attested') is False
           and overlay.get('alpha_authority') is False
           and overlay.get('execution')=='NONE'
           and overlay.get('real_money')=='NO-GO',
           "CONSUMER_CLAIMS_UNPROVEN_BUY")
    return {'status':'CONSUMER_ASOF_EQUAL_NOT_CANONICAL_RELEASE',
            'alert_authority':False, 'registered_r92_count':0}

def load_and_hash(path):
    raw=path.read_bytes()
    return json.loads(raw), git_blob(raw)

def main():
    parser=argparse.ArgumentParser()
    for key in DOCS:parser.add_argument('--'+key,required=True,type=Path)
    parser.add_argument('--manifest',required=True,type=Path,
                        help='Immutable producer file metadata; provenance MUST be validated upstream')
    parser.add_argument('--digest',type=Path)
    parser.add_argument('--overlay',type=Path)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    try:
        docs={}; actual={}
        for key in DOCS:
            docs[key],actual[key]=load_and_hash(getattr(args,key))
        manifest=json.loads(args.manifest.read_text(encoding='utf-8'))
        demand(manifest.get('schema')=='XRAY_SOURCE_EPOCH_MANIFEST_V25',"MANIFEST_SCHEMA")
        pinned=manifest.get('source_git_blobs')
        producer_commit=manifest.get('producer_head_sha')
        demand(type(producer_commit) is str,"PRODUCER_HEAD_MISSING")
        result=check_source(docs['root'],docs['master'],docs['price'],actual,pinned,producer_commit)
        demand(manifest.get('asof_et')==result['asof_et'],"MANIFEST_ASOF_MISMATCH")
        if args.digest or args.overlay:
            demand(args.digest is not None and args.overlay is not None,"CONSUMER_PAIR_INCOMPLETE")
            digest,_=load_and_hash(args.digest)
            overlay,_=load_and_hash(args.overlay)
            result['consumer']=check_consumer_date(result,digest,overlay)
    except (GateFailure, OSError, json.JSONDecodeError, TypeError, KeyError) as e:
        result={'status':'BLOCKED_NO_PUBLICATION','reason':e.code if isinstance(e,GateFailure) else type(e).__name__,
                'alert_authority':False,'registered_r92_count':0,'execution':'NONE','real_money':'NO-GO'}
        code=2
    else:
        code=0
    rendered=json.dumps(result,indent=2,ensure_ascii=False,sort_keys=True)+'\n'
    if args.output:
        args.output.write_text(rendered,encoding='utf-8')
    print(rendered,end='')
    return code

if __name__=='__main__':
    raise SystemExit(main())