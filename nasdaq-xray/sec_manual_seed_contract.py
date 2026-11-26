"""Strict offline SEC seed registry contract; exclusion evidence only."""
import json
import re
from datetime import date
from urllib.parse import urlsplit

def strict_date(v):
    if not isinstance(v,str) or not re.fullmatch(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}",v):
        raise ValueError("NONCANONICAL_DATE")
    return date.fromisoformat(v)

def cik_number(v):
    if type(v) is int:
        return v if 0<v<10**10 else None
    if isinstance(v,str) and re.fullmatch(r"[0-9]{1,10}",v):
        return int(v) or None
    return None

def sec_source_binds_cik(source,cik):
    target=cik_number(cik)
    if (target is None or type(source) is not str or not source.isascii()
            or any(ord(ch)<=32 or ord(ch)==127 for ch in source)):
        return False
    try:
        u=urlsplit(source)
        if u.scheme!="https" or u.netloc.lower()!="www.sec.gov" or u.fragment:
            return False
        landing=u.path in ("/edgar/browse/","/cgi-bin/browse-edgar")
        # Only the canonical CIK and the existing landing producer's
        # owner=exclude filter may be present; never bind a URL with an
        # unrelated action, identity override, duplicate or encoded query.
        params={}
        for part in u.query.split("&") if u.query else ():
            if re.fullmatch(r"(?i:CIK)=[0-9]{1,10}",part):
                key,value="CIK",part.split("=",1)[1]
            elif landing and part=="owner=exclude":
                key,value="owner","exclude"
            else:
                return False
            if key in params:
                return False
            params[key]=value
        q=[params["CIK"]] if "CIK" in params else []
        if q and cik_number(q[0])!=target:
            return False
        # Exact archive document, not a directory, traversal, encoded path
        # separator or arbitrary same-host resource. Preserve legacy flat
        # accession filenames and current nested filing documents.
        m=re.fullmatch(
            r"/Archives/edgar/data/([0-9]{1,10})/(?:[0-9]{18}/)?"
            r"[A-Za-z0-9_-][A-Za-z0-9._-]*\.(?:htm|html|txt|xml)",
            u.path,re.I)
        if m:
            return cik_number(m.group(1))==target
        return u.path in ("/edgar/browse/","/cgi-bin/browse-edgar") and len(q)==1
    except (ValueError,TypeError):
        return False

def exact_manual_seed_identity(row):
    """Reject coerced or unverified identity fields; never confer alpha authority."""
    if type(row) is not dict:
        return False
    cik=row.get("cik")
    sic=row.get("sic")
    blank=row.get("is_blank_check")
    classification=row.get("classification")
    return (type(cik) is str and re.fullmatch(r"[0-9]{10}",cik) is not None
            and cik_number(cik) is not None
            and type(sic) is int and 100<=sic<=9999
            and type(blank) is bool and blank==(sic==6770)
            and type(classification) is str and bool(classification.strip())
            and ((classification=="Blank Checks")==blank)
            and row.get("evidence_authority")=="SEC_EDGAR_OFFICIAL"
            and sec_source_binds_cik(row.get("source_url"),cik))


def eligible_evidence(asof,evidence,verified):
    try:
        a,e,v=map(strict_date,(asof,evidence,verified))
        return e<=v<=a and 0<=(a-e).days<=120
    except (ValueError,TypeError):
        return False

def unique_object(pairs):
    out={}
    for k,v in pairs:
        if k in out:
            raise RuntimeError("SEC_SEED_DUPLICATE_KEY:"+k)
        out[k]=v
    return out

def load_registry_document(raw):
    j=json.loads(raw,object_pairs_hook=unique_object)
    if not (isinstance(j,dict) and j.get("schema")=="XRAY_MASTER_SEC_IDENTITY_MANUAL_SEED_REGISTRY_V1"
            and j.get("execution")=="NONE" and j.get("real_money")=="NO-GO"
            and j.get("unknown_never_pass") is True
            and j.get("authority")=="OFFICIAL_SEC_EVIDENCE_DISCOVERY_SEED_ONLY"
            and isinstance(j.get("records"),dict)
            and isinstance(j.get("renewals",{}),dict)):
        raise RuntimeError("SEC_SEED_REGISTRY_HEADER_INVALID")
    if any(not k or k!=k.strip() for k in j["records"]):
        raise RuntimeError("SEC_SEED_SYMBOL_NOT_EXACT")
    return j

def select_registry_rows(j,asof,forbidden_renewals=()):
    """Keep original records and use only monotonic, same-issuer renewals
    verified no later than the requested ASOF. No override of known vetoes.
    """
    a=strict_date(asof)
    rows=dict(j["records"])
    for sym,versions in j.get("renewals",{}).items():
        old=rows.get(sym)
        if sym in forbidden_renewals or not isinstance(old,dict) or not isinstance(versions,list) or not versions:
            raise RuntimeError("SEC_SEED_RENEWAL_SCOPE_INVALID:"+sym)
        try:
            last_e=strict_date(old.get("evidence_date"))
            last_v=strict_date(old.get("verified_asof_et"))
        except ValueError as exc:
            raise RuntimeError("SEC_SEED_RENEWAL_BASE_INVALID:"+sym) from exc
        for new in versions:
            try:
                if not (isinstance(new,dict) and new.get("cik")==old.get("cik")
                        and cik_number(new.get("cik")) is not None
                        and type(old.get("sic")) is int and old["sic"]==6770
                        and type(new.get("sic")) is int and new["sic"]==6770
                        and old.get("is_blank_check") is True and new.get("is_blank_check") is True
                        and new.get("classification")=="Blank Checks"
                        and new.get("evidence_authority")=="SEC_EDGAR_OFFICIAL"
                        and isinstance(new.get("source_url"),str)
                        and re.fullmatch(r"https://www\.sec\.gov/Archives/edgar/data/[0-9]+/[0-9]+/[0-9-]+-index\.html?",new["source_url"])
                        and sec_source_binds_cik(new["source_url"],new["cik"])):
                    raise ValueError("IDENTITY_OR_SOURCE")
                e=strict_date(new.get("evidence_date"))
                v=strict_date(new.get("verified_asof_et"))
                if not (last_e<e<=v and last_v<v):
                    raise ValueError("NONMONOTONIC_EVIDENCE")
            except (ValueError,TypeError) as exc:
                raise RuntimeError("SEC_SEED_RENEWAL_INVALID:"+sym) from exc
            last_e,last_v=e,v
            if v<=a:
                rows[sym]=new
    return rows
