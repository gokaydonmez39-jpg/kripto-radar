#!/usr/bin/env python3
from copy import deepcopy
from guardian_anomaly import master_identity_partition_integrity

def base():
    return {
      "schema":"XRAY_CANONICAL_CURRENT_MASTER_MANIFEST_V1",
      "status":"PARTIAL_UNKNOWN",
      "unknown_never_pass":True,
      "queue_total":2,"raw_identity_total":3,
      "pass_count":2,"pass_symbols":["AAA","BBB"],
      "unknown_count":1,"unknown_symbols":["CCC"],
      "completion_proof":{
        "identity_authority_v6":True,
        "authority_full_identity":True,
        "full_identity":True,
        "queue_hash_exact":True,
        "queue_total_exact":True,
        "queue_unique":True,
        "asof_identity_proof_binding":True,
        "sec_spac_proof_binding":True,
        "identity_partition_policy_exact":True,
        "identity_unknown_partition_exact":True,
      }
    }

def main():
    m=base()
    assert master_identity_partition_integrity(m) is True
    x=deepcopy(m); x["unknown_symbols"]=["BBB"]
    assert master_identity_partition_integrity(x) is False
    x=deepcopy(m); x["status"]="HISTORY_COMPLETE"
    assert master_identity_partition_integrity(x) is False
    x=deepcopy(m); x["unknown_count"]=0; x["unknown_symbols"]=[]; x["raw_identity_total"]=2; x["status"]="HISTORY_COMPLETE"
    assert master_identity_partition_integrity(x) is True
    print("XRAY_GUARDIAN_IDENTITY_PARTITION_SELFTEST=PASS")

if __name__=="__main__":
    main()
