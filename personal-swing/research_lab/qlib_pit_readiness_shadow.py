"""Qlib-inspired, synthetic-only XRAY NASDAQ PIT/holdout admission probe.
No Qlib import, proprietary bars, trading actions, Sheets, or market calls.
Input provenance assertions are not independent official-source attestations.
"""
from datetime import datetime, timezone, date, timedelta
from statistics import mean, pstdev
import math
MIN_HISTORY = 500
HORIZON = 15
NO_AUTHORITY = {k: False for k in (
    "may_generate_al", "may_change_stop", "may_issue_order", "may_write_sheets",
    "may_notify", "real_pit_verified", "market_outperformance_proven")}

def _utc(raw):
    if not isinstance(raw,str):
        raise ValueError("BAD_KNOWN_AT")
    try:
        t=datetime.fromisoformat(raw.replace("Z","+00:00"))
    except ValueError as exc:
        raise ValueError("BAD_KNOWN_AT") from exc
    if t.tzinfo is None or t.utcoffset().total_seconds()!=0:
        raise ValueError("NON_UTC_PROVENANCE")
    return t.astimezone(timezone.utc)

def _number(v):
    if type(v) not in (int,float) or not math.isfinite(v):
        raise ValueError("NONFINITE_FEATURE")
    return float(v)

def check_fixture(rows, minimum=MIN_HISTORY):
    """Validate supplied evidence claims; NOT issuer or source truth."""
    if type(minimum) is not int or minimum < MIN_HISTORY:
        raise ValueError("MINIMUM_MUST_NOT_BE_WEAKENED")
    if not isinstance(rows,list) or len(rows)<minimum:
        raise ValueError("INSUFFICIENT_HISTORY")
    seen=set()
    for i,row in enumerate(rows):
        if not isinstance(row,dict) or type(row.get("index")) is not int or row["index"]!=i:
            raise ValueError("NONCONTIGUOUS_SESSION_INDEX")
        day=row.get("session")
        if not isinstance(day,str) or day in seen or len(day)!=10:
            raise ValueError("DUPLICATE_OR_BAD_SESSION")
        try:
            if datetime.strptime(day,"%Y-%m-%d").strftime("%Y-%m-%d")!=day:
                raise ValueError("BAD_SESSION_DATE")
        except ValueError as exc:
            raise ValueError("BAD_SESSION_DATE") from exc
        seen.add(day)
        if not isinstance(row.get("issuer_id"),str) or not row["issuer_id"]:
            raise ValueError("MISSING_ISSUER_IDENTITY")
        if row.get("venue")!="IEX" or row.get("basis")!="RAW":
            raise ValueError("SOURCE_CONTRACT_DRIFT")
        if row.get("data_rights_attested") is not True:
            raise ValueError("RIGHTS_NOT_ATTESTED")
        if _utc(row.get("first_known_at_utc"))>_utc(row.get("decision_cutoff_utc")):
            raise ValueError("PIT_LOOKAHEAD")
        _number(row.get("feature"))
        if type(row.get("label_end_index")) is not int or row["label_end_index"]<i:
            raise ValueError("INVALID_LABEL_HORIZON")
    if any(rows[j]["session"]>=rows[j+1]["session"] for j in range(len(rows)-1)):
        raise ValueError("SESSION_ORDER_DRIFT")
    return len(rows)

def purged_chronological_split(rows, *, train_end=400, label_horizon=HORIZON):
    check_fixture(rows)
    if type(train_end) is not int or type(label_horizon) is not int or label_horizon<HORIZON:
        raise ValueError("BAD_SPLIT_PARAMETERS")
    if train_end<=100 or train_end>=len(rows)-30:
        raise ValueError("INSUFFICIENT_TEST_WINDOW")
    if any(row["label_end_index"]<i+label_horizon for i,row in enumerate(rows)):
        raise ValueError("LABEL_HORIZON_UNDERSPECIFIED")
    train=tuple(i for i,row in enumerate(rows[:train_end]) if row["label_end_index"]<train_end)
    test=tuple(range(train_end,len(rows)))
    if len(train)<100 or not test or max(train)>=min(test):
        raise ValueError("LEAK_OR_TRAIN_SHORT")
    if any(rows[i]["label_end_index"]>=train_end for i in train):
        raise ValueError("OVERLAPPING_LABEL")
    return train,test

def train_only_scaler(rows,train,test):
    if not train or not test or set(train)&set(test) or max(train)>=min(test):
        raise ValueError("UNSAFE_FEATURE_SPLIT")
    if any(type(i) is not int or i<0 or i>=len(rows) for i in (*train,*test)):
        raise ValueError("BAD_FEATURE_INDEX")
    vals=[_number(rows[i]["feature"]) for i in train]
    mu=mean(vals); sd=pstdev(vals)
    if sd<=0: raise ValueError("ZERO_VARIANCE")
    out=tuple((_number(rows[i]["feature"])-mu)/sd for i in test)
    if not all(math.isfinite(x) for x in out):
        raise ValueError("NONFINITE_TRANSFORM")
    return {"train_mean":mu,"train_std":sd,"test_transformed":out}

def synthetic_rows(count=520):
    if type(count) is not int or count<MIN_HISTORY:
        raise ValueError("INSUFFICIENT_HISTORY")
    start=date(2023,1,2)
    # Artificial consecutive calendar days, NEVER claims real XNAS session proof.
    return [{"index":i,"session":(start+timedelta(days=i)).isoformat(),
             "issuer_id":"SYNTHETIC_ISSUER","venue":"IEX","basis":"RAW",
             "data_rights_attested":True,"first_known_at_utc":"2023-01-01T10:00:00Z",
             "decision_cutoff_utc":"2025-01-01T23:00:00Z",
             "feature":float((i%23)-11),"label_end_index":i+HORIZON}
            for i in range(count)]

def report():
    rows=synthetic_rows()
    train,test=purged_chronological_split(rows)
    scale=train_only_scaler(rows,train,test)
    return {"schema":"XRAY_QLIB_PIT_SHADOW_V1","synthetic_only":True,
            "history_contract_minimum":MIN_HISTORY,"synthetic_rows":len(rows),
            "train_rows":len(train),"test_rows":len(test),
            "scaler_training_rows":len(train),"scaler_std_positive":scale["train_std"]>0,
            "historical_xnas_sessions_verified":0,"issuer_lineage_verified":False,
            "provider_first_seen_independently_verified":False,
            "rights_independently_verified":False,"qlib_executed":False,
            "external_requests":0,"no_authority":NO_AUTHORITY,
            "result":"SYNTHETIC_CONTRACT_ONLY_REAL_DATA_NO_GO"}

if __name__=="__main__":
    import json
    print(json.dumps(report(),sort_keys=True))
