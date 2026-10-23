#!/usr/bin/env python3
"""XRAY vetted reference catalog & dependency-contract audit. Offline and read-only.

No provider access, licensed data, broker connections, orders or certified AL.
A curated reference list is NOT a real-time proof of market data or trading rights.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

SCHEMA = 'XRAY_V42_CURATED_SOURCE_TO_GATE_CONTRACT_V1'
GATES = tuple('A'+str(i) for i in range(8))
SAFETY = {'execution':'NONE','real_money':'NO-GO','broker':False,
          'source_authority':False,'canonical_price_pass':False,
          'issuer_mc_pass':False,'g9_pass':False,'c417_pass':False,
          'registered_r92_count':0,'iphone_receipt_attested':False,
          'unknown_never_pass':True,'orders':[]}

class GateAuditFailure(ValueError):
    pass

def need(flag, name):
    if not flag:
        raise GateAuditFailure('XRAY_V42_'+name)

def audit(obj):
    """Fail-closed *schema & claims* check, not external compliance attestation."""
    need(type(obj) is dict and obj.get('schema')==SCHEMA,'SCHEMA')
    need(obj.get('origin_source_count')==262 and
         obj.get('origin_archive')=='XRAY_v41_RT262','ARCHIVE_EPOCH')
    for k,v in SAFETY.items():
        need(type(obj.get(k)) is type(v) and obj[k]==v,'SAFETY_'+k)
    need(type(obj.get('ranked_sources')) is list and
         len(obj['ranked_sources'])>=24,'SOURCE_MINIMUM')
    ids=set(); urls=set(); ranks=[]; external=[]
    for s in obj['ranked_sources']:
        need(type(s) is dict,'SOURCE_TYPE')
        for k in ('source_id','name','url','gate','integration','provenance'):
            need(type(s.get(k)) is str and bool(s[k]),'SOURCE_FIELD_'+k)
        need(s['source_id'].startswith('RT-') and s['source_id'][3:].isdigit(), 'SOURCE_ID')
        need(s['source_id'] not in ids and s['url'] not in urls,'DUPLICATE_SOURCE')
        ids.add(s['source_id']); urls.add(s['url']); ranks.append(s.get('rank'))
        need(s['url'].startswith('https://') and ' ' not in s['url'],'SOURCE_HTTPS')
        need(s['gate'] in GATES or s['gate']=='HOLD','SOURCE_GATE')
        need(s['verified_link_in_archive'] is True,'ARCHIVE_SOURCE')
        if s['gate']=='HOLD':
            need(s['integration']=='RESEARCH_PATTERN_ONLY_NOT_INSTALLED','HOLD_NOT_INSTALLED')
            external.append(s['source_id'])
        else:
            need(s['integration']=='READ_ONLY_ACCEPTANCE_REFERENCE','NO_EXECUTABLE_PLUGIN')
    need(ranks==list(range(1,len(ranks)+1)),'ORDERED_SOURCE_RANK')
    need(type(obj.get('gates')) is list and len(obj['gates'])==len(GATES),'GATE_SET_SIZE')
    byid={}
    for g in obj['gates']:
        need(type(g) is dict and g.get('id') in GATES,'GATE_ID')
        need(g['id'] not in byid,'DUPLICATE_GATE')
        byid[g['id']]=g
        need(type(g.get('description')) is str and bool(g['description']),'GATE_DESCRIPTION')
        need(type(g.get('acceptance')) is str and bool(g['acceptance']),'GATE_ACCEPTANCE')
        need(type(g.get('state')) is str and
             (g['state'].startswith('BLOCKED_') or g['state']=='PARTIAL_OFFICIAL_DOCS_ONLY'),
             'UNSUPPORTED_PROMOTION')
        need(g.get('independently_attested') is False and
             g.get('release_ready') is False, 'UNJUSTIFIED_ATTESTATION')
        need(type(g.get('depends_on')) is list,'GATE_DEPENDENCY_FORMAT')
        need(type(g.get('source_ids')) is list and len(g['source_ids'])>0,'GATE_SOURCE_EVIDENCE')
        need(all(type(a) is str for a in g['source_ids']),'GATE_SOURCE_ID_TYPES')
        need(set(g['source_ids'])=={s['source_id'] for s in obj['ranked_sources'] if s['gate']==g['id']},
             'GATE_SOURCE_BINDING')
    need(set(byid)==set(GATES),'MISSING_GATE')
    visited=set(); active=set()
    def walk(id):
        need(id in byid,'UNKNOWN_DEPENDENCY')
        need(id not in active,'CYCLIC_DEPENDENCY')
        if id in visited: return
        active.add(id)
        for dep in byid[id]['depends_on']:
            need(type(dep) is str,'DEPENDENCY_TYPE')
            walk(dep)
        active.remove(id);visited.add(id)
    for id in GATES: walk(id)
    need(byid['A7']['depends_on']==['A3','A4','A5','A6'],'FINAL_INDEPENDENT_GATES')
    need('A0' in byid['A2']['depends_on'] and 'A0' not in byid['A1']['depends_on'],
         'RIGHTS_BEFORE_VENDOR_READ')
    notes=obj.get('design_notes',{})
    for k in ('known_alpaca_repaired_snapshot_not_revalidated',
              'generic_plan_does_not_grant_account_entitlement',
              'third_party_roundtable_tools_not_installed',
              'no_external_provider_request_performed',
              'draft_pr250_not_merged',
              'local_shadow_contract_not_certified_production'):
        need(type(notes.get(k)) is bool and notes[k] is True,'CRITICAL_NOTE_'+k)
    return {'schema':'XRAY_V42_AUDIT_RESULT_RESEARCH_ONLY','status':'BLOCKED_REAL_WORLD_ATTESTATION',
            'gate_count':len(byid),'curated_source_count':len(ids),'external_tools_held':len(external),
            'release_ready':False,'execution':'NONE','real_money':'NO-GO',
            'registered_r92_count':0,'unknown_never_pass':True}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('catalog',type=Path)
    args=parser.parse_args()
    result=audit(json.loads(args.catalog.read_text(encoding='utf-8')))
    print(json.dumps(result,sort_keys=True))

if __name__=='__main__':main()