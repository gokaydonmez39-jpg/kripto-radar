#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from cryptography.fernet import Fernet

import account_longbridge_mcp_v2_bootstrap as boot
import account_longbridge_mcp_v2_vault as vault


class Obj:
    def __init__(self, *, input_schema=None, structured_content=None, content=None, is_error=False):
        self.inputSchema=input_schema
        self.structured_content=structured_content
        self.content=[] if content is None else content
        self.is_error=is_error


class Text:
    def __init__(self,text): self.text=text


def expect_error(fn, text: str):
    try:
        fn()
    except Exception as exc:
        assert text in str(exc), (text, repr(exc))
        return
    raise AssertionError(f"expected {text}")


def main():
    # The one-time auth code is NOT an encryption key.
    expect_error(lambda: vault.resolve_vault_key({}), "VAULT_KEY_MISSING")
    key=Fernet.generate_key().decode()
    assert vault.resolve_vault_key({vault.FERNET_KEY_ENV:key})==key

    tool=Obj(input_schema={
        "type":"object",
        "properties":{"auth_code":{"type":"string"}},
        "required":["auth_code"],
    })
    assert boot._auth_arg_name(tool)=="auth_code"

    assert boot._candidate_token({"access_token":"private-bearer-token-value-123"})=="private-bearer-token-value-123"
    assert boot._candidate_token("Authorization: Bearer private-bearer-token-value-456")=="private-bearer-token-value-456"
    result=Obj(structured_content={"token":"private-bearer-token-value-789"})
    assert boot._extract_token(result)=="private-bearer-token-value-789"

    manifest={"account_balance","stock_positions","quote","watchlist"}
    payload=boot.build_vault_payload("private-bearer-token-value-xyz",manifest,now_epoch=1_000_000)
    assert payload["schema"]=="XRAY_LONGBRIDGE_OFFICIAL_MCP_AGENT_BEARER_V1"
    assert payload["main_endpoint"]=="https://mcp.longbridge.com"
    assert payload["agent_endpoint"]=="https://mcp.longbridge.com/agent"
    assert payload["account_tools_verified"] is True
    assert payload["write_surface_absent"] is True

    expect_error(
        lambda: boot.build_vault_payload("private-bearer-token-value-xyz",{"account_balance"}),
        "ACCOUNT_TOOL_MANIFEST_NOT_VERIFIED",
    )
    expect_error(
        lambda: boot.build_vault_payload(
            "private-bearer-token-value-xyz",
            {"account_balance","stock_positions","submit_order"},
        ),
        "WRITE_SURFACE_PRESENT",
    )

    encoded=vault.encrypt_payload(payload,key)
    assert b"private-bearer-token-value-xyz" not in encoded
    decoded=vault.decrypt_payload(encoded,key)
    assert decoded==payload

    with tempfile.TemporaryDirectory() as td:
        p=Path(td)/"token.enc"
        vault.save_vault(payload,p,key=key)
        raw=p.read_bytes()
        assert b"private-bearer-token-value-xyz" not in raw
        loaded=vault.load_vault(p,key=key)
        assert loaded==payload
        assert vault.bearer_from_vault(loaded)=="private-bearer-token-value-xyz"

    bad=dict(payload)
    bad["write_surface_absent"]=False
    expect_error(lambda: vault.validate_payload(bad),"VAULT_WRITE_SURFACE_NOT_ABSENT")

    public=boot._public("PASS","TEST")
    encoded_public=json.dumps(public).lower()
    for forbidden in (
        "private-bearer-token-value-123",
        "private-bearer-token-value-456",
        "private-bearer-token-value-789",
        "private-bearer-token-value-xyz",
    ):
        assert forbidden not in encoded_public
    assert public["private_values_persisted"] is False
    assert public["secret_values_persisted"] is False
    assert public["execution"]=="NONE"
    assert public["real_money"]=="NO-GO"
    assert public["main_endpoint"]=="https://mcp.longbridge.com"
    assert public["agent_endpoint"]=="https://mcp.longbridge.com/agent"

    print("XRAY_ACCOUNT_MCP_V2_VAULT_SELFTEST=PASS")


if __name__=="__main__":
    main()
