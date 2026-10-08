#!/usr/bin/env python3
"""Fail closed: a non-6770 SEC SIC does not prove completed de-SPAC.

An acquisition/blank-check security can carry a target-sector SIC while the
business combination remains proposed. Only a separate, exact-ASOF issuer
closing/merger completion witness may permit a successor operating PASS.
Current policy does not possess one; ambiguous rows stay UNKNOWN.
"""
def nonblank_requires_completion(spac_name_suspect: bool, sic) -> bool:
    try:
        n=int(sic)
    except (ValueError,TypeError):
        return bool(spac_name_suspect)
    return bool(spac_name_suspect and n!=6770)


def selftest():
    assert nonblank_requires_completion(True,7374)  # ALIS proposed Goodvision merger
    assert nonblank_requires_completion(True,3569)  # CCXI proposed Agility merger
    assert nonblank_requires_completion(True,None)
    assert not nonblank_requires_completion(True,6770)
    assert not nonblank_requires_completion(False,7374)
    print("XRAY_SPAC_NONBLANK_SIC_PREMERGER_VETO_SELFTEST=PASS")


if __name__=="__main__":
    selftest()
