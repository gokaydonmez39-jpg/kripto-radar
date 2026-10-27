"""Fail-closed offline DSR witness. No market data, no AL decision, no broker or alerts.

The observed Sharpe uses per-observation returns (NOT annualized).
Requires a documented complete parameter search count, independent holdout,
and variance of observed Sharpe estimates. Output is RESEARCH_ONLY.
"""
import math
from honest_backtest import deflated_sharpe_ratio, probabilistic_sharpe_ratio

class InsufficientEvidence(ValueError):
    pass

def deflated_research_confidence(*, sr, n_obs, skew, kurt, n_trials, var_sr):
    for name, value in (("sr",sr),("skew",skew),("kurt",kurt),("var_sr",var_sr)):
        if type(value) not in (int,float) or not math.isfinite(value):
            raise InsufficientEvidence("INVALID_"+name.upper())
    if type(n_obs) is not int or n_obs < 3:
        raise InsufficientEvidence("MISSING_EFFECTIVE_SAMPLE_SIZE")
    if type(n_trials) is not int or n_trials < 2:
        raise InsufficientEvidence("SEARCH_TRIAL_COUNT_REQUIRED")
    if var_sr <= 0 or kurt <= 0:
        raise InsufficientEvidence("INVALID_ESTIMATION_MOMENT")
    result=deflated_sharpe_ratio(sr=sr,n_obs=n_obs,skew=skew,kurt=kurt,n_trials=n_trials,var_sr=var_sr)
    naive=probabilistic_sharpe_ratio(sr=sr,n_obs=n_obs,skew=skew,kurt=kurt)
    if not math.isfinite(result) or not 0<=result<=1 or result>naive+1e-12:
        raise InsufficientEvidence("INCONSISTENT_DEFLATION")
    return {"dsr":result,"naive_psr":naive,"n_obs":n_obs,"n_trials":n_trials,
            "status":"RESEARCH_ONLY_NOT_PROFIT_FORECAST"}
