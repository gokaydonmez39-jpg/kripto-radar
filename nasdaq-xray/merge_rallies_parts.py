#!/usr/bin/env python3
import hashlib, json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
STATE=ROOT/"eastmoney_state.json"
OUT=ROOT/"rallies_recovery_summary.json"

def sha_lines(xs):
    return hashlib.sha256("\n".join(xs).encode()).hexdigest()

st=json.loads(STATE.read_text(encoding="utf-8"))
queue=st.get("queue") or []
if not queue:
    raise RuntimeError("QUEUE_MISSING")
parts=[]
for i in range(1,5):
    p=json.loads((ROOT/f"rallies_dv20_part{i}.json").read_text(encoding="utf-8"))
    if p.get("queue_hash")!=st.get("queue_hash") or p.get("queue_total")!=len(queue):
        raise RuntimeError(f"PART_QUEUE_MISMATCH_{i}")
    parts.append(p)

dates=[]
merged={}
date_counts={}
for p in parts:
    dates.extend(p["dates"])
    date_counts.update(p.get("counts") or {})
    for sym,rows in (p.get("data") or {}).items():
        merged.setdefault(sym,{}).update(rows)

if len(dates)!=20 or len(set(dates))!=20 or dates[-1]!="2026-09-29":
    raise RuntimeError("EXPECTED20_INVALID")

def med20(vals):
    a=sorted(vals)
    return (a[9]+a[10])/2.0

groups={"PASS_PRICE_DV20":[],"FAIL_PRICE":[],"FAIL_DV20":[],"MISSING_EXACT20":[]}
pass_metrics={}
missing_detail={}
for sym in queue:
    rows=merged.get(sym,{})
    missing=[d for d in dates if d not in rows]
    if missing:
        groups["MISSING_EXACT20"].append(sym)
        missing_detail[sym]=missing
        continue
    price=float(rows["2026-09-29"][0])
    dv20=med20([float(rows[d][0])*float(rows[d][1]) for d in dates])
    if price<=10:
        groups["FAIL_PRICE"].append(sym)
    elif dv20<50_000_000:
        groups["FAIL_DV20"].append(sym)
    else:
        groups["PASS_PRICE_DV20"].append(sym)
        pass_metrics[sym]={"price":price,"dv20":dv20}

for k in groups:
    groups[k]=sorted(groups[k])

classification_serial=[]
for status in sorted(groups):
    classification_serial.extend(status+"|"+s for s in groups[status])

out={
  "schema":"XRAY_RALLIES_PRIMARY_DV20_RECOVERY_SUMMARY_V1",
  "task_id":"6a825366222081918997094d76e6ae46",
  "role":"ZERO_ALPHA_NEW_EPOCH_PRIMARY_DV20_EVIDENCE",
  "asof_et":"2026-09-29",
  "expected20":dates,
  "identity_queue_hash":st.get("queue_hash"),
  "identity_queue_total":len(queue),
  "provider":"RALLIES_GET_OHCV_DATA_FOR_ALL_TICKERS_FOR_A_DATE",
  "price_threshold_strict_gt":10,
  "dv20_threshold":50000000,
  "counts":{k:len(v) for k,v in groups.items()},
  "group_hashes":{k:sha_lines(v) for k,v in groups.items()},
  "classification_hash":sha_lines(classification_serial),
  "date_counts":date_counts,
  "pass_symbols":groups["PASS_PRICE_DV20"],
  "pass_metrics":pass_metrics,
  "missing_symbols":groups["MISSING_EXACT20"],
  "missing_detail":missing_detail,
  "fail_price_hash":sha_lines(groups["FAIL_PRICE"]),
  "fail_dv20_hash":sha_lines(groups["FAIL_DV20"]),
  "execution":"NONE",
  "real_money":"NO-GO",
  "unknown_never_pass":True
}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n",encoding="utf-8")
for status,symbols in groups.items():
    (ROOT/f"rallies_group_{status.lower()}.txt").write_text(",".join(symbols)+"\n",encoding="utf-8")
print(json.dumps({
 "queue_total":len(queue),
 "counts":out["counts"],
 "classification_hash":out["classification_hash"],
 "pass_count":len(out["pass_symbols"]),
 "missing_count":len(out["missing_symbols"])
},sort_keys=True))
