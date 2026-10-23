"""Synthetic negative tests. No HTTP and no equities/order activity."""
import unittest
import copy
import json
from pathlib import Path
from xray_v42_offline_source_gate_audit import audit,GateAuditFailure
CAT=json.loads((Path(__file__).parent/'xray_v42_ranked_source_gate_contract.json').read_text())

class CatalogTest(unittest.TestCase):
 def test_true_archive_catalog_is_research_only(self):
  result=audit(CAT)
  self.assertEqual(result['gate_count'],8)
  self.assertFalse(result['release_ready'])
  self.assertEqual(result['registered_r92_count'],0)
 def bad(self,mutate):
  item=copy.deepcopy(CAT)
  mutate(item)
  with self.assertRaises(GateAuditFailure):audit(item)
 def test_false_price_promotion(self): self.bad(lambda x:x.update(canonical_price_pass=True))
 def test_false_r92(self): self.bad(lambda x:x.update(registered_r92_count=1))
 def test_false_rights_promotion(self): self.bad(lambda x:x['gates'][0].update(independently_attested=True,release_ready=True,state='PASS'))
 def test_break_vendor_rights_dependency(self):self.bad(lambda x:x['gates'][2].update(depends_on=['A1']))
 def test_missing_gate(self): self.bad(lambda x:x['gates'].pop())
 def test_dependency_cycle(self):self.bad(lambda x:x['gates'][0].update(depends_on=['A7']))
 def test_missing_source_evidence(self):self.bad(lambda x:x['gates'][3].update(source_ids=[]))
 def test_duplicate_source(self):self.bad(lambda x:x['ranked_sources'][1].update(url=x['ranked_sources'][0]['url']))
 def test_unreviewed_tool_install(self):self.bad(lambda x:x['ranked_sources'][-1].update(integration='INSTALLED'))
 def test_unattested_sample_not_entitlement(self):self.bad(lambda x:x['design_notes'].update(generic_plan_does_not_grant_account_entitlement=False))
 def test_reversed_rank(self):self.bad(lambda x:x['ranked_sources'][0].update(rank=30))
 def test_nondocumented_status(self): self.bad(lambda x:x['gates'][0].update(state='PASS'))
 def test_false_execution(self): self.bad(lambda x:x.update(execution='LIVE'))
 def test_false_source_authority(self):self.bad(lambda x:x.update(source_authority=True))
 def test_false_release_flag_only(self):self.bad(lambda x:x['gates'][5].update(release_ready=True))
 def test_remove_critical_note(self):self.bad(lambda x:x['design_notes'].pop('no_external_provider_request_performed'))

if __name__=='__main__':unittest.main()