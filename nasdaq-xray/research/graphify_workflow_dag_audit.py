#!/usr/bin/env python3
"""Offline GitHub Actions DAG audit complementing Graphify's code-only AST."""
import argparse
import json
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
import yaml

SCHEMA="XRAY_GRAPHIFY_ACTIONS_DAG_RESEARCH_V1"
def require(ok,why):
    if not ok: raise ValueError("XRAY_ACTIONS_DAG_"+why)
def names(v):
    if isinstance(v,str): return [v]
    if isinstance(v,list) and all(isinstance(x,str) for x in v): return v
    return []

def audit(directory):
    require(directory.is_dir(),"NO_DIR")
    paths=sorted(p for p in directory.iterdir() if p.suffix in (".yml",".yaml"))
    require(bool(paths),"NO_FILES")
    docs={}; byname=defaultdict(list)
    for p in paths:
        require(p.is_file() and not p.is_symlink() and p.stat().st_size<1000000,
                "FILE_UNSAFE:"+p.name)
        d=yaml.load(p.read_text(encoding="utf8"),Loader=yaml.BaseLoader)
        require(isinstance(d,dict),"INVALID_YAML:"+p.name)
        require(isinstance(d.get("jobs",{}),dict),"INVALID_JOBS:"+p.name)
        n=str(d.get("name") or p.name)
        require(0<len(n)<=160,"INVALID_NAME")
        docs[p.name]=d;byname[n].append(p.name)
    edges=set();bad=[];dynamic=[]; filenames=set(docs)
    for p,d in docs.items():
        jobs=d.get("jobs") or {}
        for jobid,job in jobs.items():
            require(isinstance(job,dict),"BAD_JOB:"+p)
            dest=p+"::"+str(jobid)
            for pre in names(job.get("needs",[])):
                if "$" in pre and "{{" in pre:
                    dynamic.append(dest);continue
                if pre not in jobs:
                    bad.append({"type":"UNBOUND_NEEDS","source":dest,
                                "target":p+"::"+pre})
                else:edges.add(("needs",p+"::"+pre,dest))
            reuse=str(job.get("uses") or "")
            if reuse.startswith("./.github/workflows/"):
                target=Path(reuse.split("@")[0]).name
                if target not in filenames:
                    bad.append({"type":"UNBOUND_REUSABLE","source":p,"target":target})
                else:edges.add(("reusable",p,target))
        events=d.get("on") or {}
        if isinstance(events,dict) and "workflow_run" in events:
            wr=events["workflow_run"]
            if not isinstance(wr,dict):
                dynamic.append(p);continue
            for source in names(wr.get("workflows",[])):
                matches=byname.get(source,[])
                if len(matches)==1:edges.add(("workflow_run",matches[0],p))
                else:bad.append({"type":"UNBOUND_OR_AMBIGUOUS_WORKFLOW_RUN",
                                 "source":p,"target":source,"matches":matches})
    adj=defaultdict(set)
    for kind,a,b in edges:
        if kind=="workflow_run":adj[a].add(b)
    long_or_cycles=[]
    for start in sorted(adj):
        stack=[(start,(start,))]
        while stack:
            node,path=stack.pop()
            if len(path)>4:
                long_or_cycles.append(list(path));continue
            for n in adj.get(node,()):
                if n in path:long_or_cycles.append(list(path)+[n])
                else:stack.append((n,path+(n,)))
        if len(long_or_cycles)>=15:break
    return {
        "schema":SCHEMA,"workflow_count":len(docs),
        "declared_edge_count":len(edges),
        "edge_types":dict(Counter(k for k,_,_ in edges)),
        "unresolved_count":len(bad),
        "unresolved_types":dict(Counter(x["type"] for x in bad)),
        "unresolved_sample":bad[:20],
        "unclassified_dynamic_count":len(dynamic),
        "long_or_cyclic_workflow_run_count":len(long_or_cycles),
        "long_or_cyclic_sample":long_or_cycles[:8],
        "graph_proof":"DECLARATIONS_ONLY_NOT_RUNTIME",
        "github_runner_execution_verified":False,
        "llm_calls":0,"vendor_market_calls":0,
        "provider_entitlement_proven":False,
        "primary_pass_created":False,"r92_created":False,
        "execution":"NONE","real_money":"NO-GO","unknown_never_pass":True,
    }

def selftest():
    with tempfile.TemporaryDirectory() as t:
        p=Path(t)
        (p/"a.yml").write_text("name: A\non:\n  push:\njobs:\n  a: {}\n")
        (p/"b.yml").write_text("name: B\non:\n  workflow_run:\n    workflows: [A]\njobs:\n  b:\n    needs: [missing]\n")
        x=audit(p)
        require(x["unresolved_types"].get("UNBOUND_NEEDS")==1,"NEG_NEEDS")
        require(x["edge_types"]["workflow_run"]==1,"POS_WORKFLOW_RUN")
        (p/"b.yml").write_text("name: B\non:\n  workflow_run:\n    workflows: [A]\njobs:\n  a: {}\n  b:\n    needs: [a]\n")
        require(audit(p)["unresolved_count"]==0,"POS_NEEDS")
        (p/"a.yml").write_text("name: A\non:\n  workflow_run:\n    workflows: [NOT_PRESENT]\n")
        require(audit(p)["unresolved_types"].get(
            "UNBOUND_OR_AMBIGUOUS_WORKFLOW_RUN")==1,"NEG_WORKFLOW_RUN")
        (p/"a.yml").write_text("name: A\non:\n  workflow_run:\n    workflows: [B]\n")
        (p/"b.yml").write_text("name: B\non:\n  workflow_run:\n    workflows: [A]\n")
        checked=audit(p)
        require(checked["long_or_cyclic_workflow_run_count"]>0,
                "CYCLE_MUST_BE_SURFACED")
    print("XRAY_GRAPHIFY_ACTIONS_DAG=PASS_3_NEG_POS_OFFLINE_NO_ALPHA")

if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("--selftest",action="store_true")
    a.add_argument("--dir",type=Path,default=Path(".github/workflows"))
    opts=a.parse_args()
    if opts.selftest:selftest()
    else:print(json.dumps(audit(opts.dir),sort_keys=True))
