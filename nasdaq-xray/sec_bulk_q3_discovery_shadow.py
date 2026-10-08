#!/usr/bin/env python3
"""Offline, research-only SEC financial dataset probe: cannot create AL/PASS."""
from __future__ import annotations
import argparse, csv, datetime as dt, hashlib, io, json, pathlib, re, zipfile
ASOF="2026-10-07"
REQUIRED={"adsh","cik","sic","name","filed","form"}
def read_candidates(zip_path:pathlib.Path,asof:str=ASOF):
    cutoff=dt.date.fromisoformat(asof)
    with zipfile.ZipFile(zip_path) as z:
        entries=[i for i in z.infolist() if i.filename.lower().split("/")[-1]=="sub.txt"]
        if len(entries)!=1 or entries[0].file_size>250_000_000:
            raise ValueError("SEC_SUB_MISSING_DUPLICATED_OR_TOO_LARGE")
        with z.open(entries[0]) as fh:
            text=fh.read(250_000_001)
        if len(text)>250_000_000:raise ValueError("SEC_SUB_TOO_LARGE")
    reader=csv.DictReader(io.StringIO(text.decode("utf-8-sig")),delimiter="\t")
    if not REQUIRED.issubset(set(reader.fieldnames or [])):
        raise ValueError("SEC_SUB_FIELDS_INCOMPLETE")
    most_recent={}
    for row in reader:
        cik=str(row.get("cik") or "").strip().zfill(10)
        filed=str(row.get("filed") or "")
        sic=str(row.get("sic") or "")
        accession=str(row.get("adsh") or "")
        try: day=dt.date.fromisoformat(filed)
        except ValueError:continue
        if (day>cutoff or len(cik)!=10 or not cik.isdigit()
             or not re.fullmatch(r"[0-9]{10}-[0-9]{2}-[0-9]{6}",accession)
             or not re.fullmatch(r"[0-9]{4}",sic)):
            continue
        record={"cik":cik,"filed":filed,"sic":int(sic),"form":row.get("form"),
                "name":row.get("name"),"accession":accession}
        if cik not in most_recent or (filed,accession)>(most_recent[cik]["filed"],most_recent[cik]["accession"]):
            most_recent[cik]=record
    positives={k:v for k,v in most_recent.items() if v["sic"]==6770 and
        0<=(cutoff-dt.date.fromisoformat(v["filed"])).days<=120}
    return positives
def selftest():
    import tempfile
    s=("adsh\tcik\tsic\tname\tfiled\tform\n"
       "0000000001-26-000001\t123\t6770\tAlpha Acquisition\t2026-09-20\t10-Q\n"
       "0000000001-26-000002\t123\t7374\tAlpha Acquisition\t2026-09-29\t8-K\n"
       "0000000002-26-000001\t456\t6770\tBeta Acquisition\t2026-08-05\t10-Q\n"
       "0000000003-26-000001\t789\t6770\tGamma Acquisition\t2026-10-09\t8-K\n"
       "0000000004-26-000001\t777\t6770\tOld Acquisition\t2026-01-01\t10-K\n")
    with tempfile.TemporaryDirectory() as td:
        f=pathlib.Path(td)/"fixture.zip"
        with zipfile.ZipFile(f,"w") as z:z.writestr("sub.txt",s)
        got=read_candidates(f)
        assert set(got)=={"0000000456"}
        assert got["0000000456"]["filed"]=="2026-08-05"
        try:read_candidates(f,"bad");raise AssertionError("BAD_DATE_ACCEPTED")
        except ValueError:pass
    print("XRAY_SEC_BULK_SHADOW_SELFTEST=PASS zero_alpha=true")
def main():
    a=argparse.ArgumentParser()
    a.add_argument("--selftest",action="store_true")
    a.add_argument("--zip",type=pathlib.Path)
    a.add_argument("--out",type=pathlib.Path)
    x=a.parse_args()
    if x.selftest:selftest();return
    if not x.zip or not x.out:a.error("--zip and --out required")
    sha=hashlib.sha256(x.zip.read_bytes()).hexdigest()
    candidates=read_candidates(x.zip)
    d={"schema":"XRAY_SEC_BULK_SIC_DISCOVERY_SHADOW_V1",
       "asof_et":ASOF,"source_sha256":sha,"candidate_count":len(candidates),
       "records":candidates,"status":"RESEARCH_ONLY_OFFICIAL_FILING_REQUIRED",
       "execution":"NONE","real_money":"NO-GO","alpha_authority":False,
       "strict_g9_pass":False,"account_pass":False,"master_pass":False}
    x.out.write_text(json.dumps(d,sort_keys=True,indent=2)+"\n")
    print("XRAY_SEC_BULK_RESEARCH_ONLY candidates="+str(len(candidates)))
if __name__=="__main__":main()
