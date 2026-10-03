# XRAY ACCOUNT Bootstrap Runbook — Longbridge Hosted MCP /v2

Status: **USER SECRET BOOTSTRAP REQUIRED**

Safety invariants:
- XRAY execution remains `NONE`; `REAL_MONEY=NO-GO`.
- Generate a Longbridge Agent Auth Code with **Account** permission only.
- Do **not** grant trading/write permission for XRAY.
- Never paste the Agent Auth Code, Bearer token, refresh token, or Fernet key into chat, issues, commits, logs, or repository files.
- The repository stores only Fernet-encrypted OAuth token ciphertext.

## Why this path exists

The audited official upstream repository `longbridge/longbridge-mcp` defines:
- `account.read` production scope id **6**, including `account_balance` and `stock_positions`.
- `trade.write` production scope id **11**.
- `https://mcp.longbridge.com/v2` as a restricted default-out allowlist that excludes TradeWrite and money-movement tools.
- `https://mcp.longbridge.com/oauth2/token` as the OAuth token/refresh proxy.

XRAY additionally checks the exposed tool manifest before reading account state and fails closed if known write tools appear.

## One-time bootstrap

### 1. Create the independent vault key

Generate a Fernet-compatible key in a trusted local environment. Example with Python:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Copy the output directly into the GitHub Actions secret named:

`XRAY_ACCOUNT_TOKEN_FERNET_KEY`

Do not save the key in this repository.

### 2. Generate a fresh Longbridge Agent Auth Code

Open:

`https://open.longbridge.com/connect`

Authorize **Account** permission. Do not select trading/write permission for XRAY.

The code is one-time and short-lived. Put it directly into the GitHub Actions repository secret:

`LONGBRIDGE_AGENT_AUTH_CODE`

Do not post it anywhere else.

### 3. Run Final Factory immediately

GitHub repository -> **Actions** -> **XRAY Canonical Current Final Factory** -> **Run workflow** on `main`.

The workflow must:
1. run all pre-secret selftests;
2. refuse to consume the Agent Auth Code if the independent Fernet key is missing;
3. exchange the one-time code;
4. require `account.read` and reject `trade.write`;
5. encrypt access+refresh token state;
6. commit only ciphertext;
7. restart/read the persisted vault;
8. verify the restricted `/v2` manifest;
9. call only `account_balance` and `stock_positions`;
10. create ACCOUNT_PASS only from fresh same-run parseable results and exact current adapter bindings.

## Expected safe outputs

Before secrets are configured:
- `XRAY_ACCOUNT_V2_RUNTIME=NO_SECRET_NETWORK_FREE`
- status `BLOCKED_MISSING_CREDENTIALS`

After successful one-time bootstrap:
- encrypted vault file exists at `nasdaq-xray/account_longbridge_mcp_v2_token.enc`
- no plaintext token appears in git/logs
- a fresh restarted Final Factory must obtain same-run account reads before ACCOUNT_PASS
- future OAuth refresh rotation is re-encrypted into the vault before account reads

## Fail-closed conditions

Any of the following must remain BLOCKED/UNKNOWN, never PASS:
- Fernet key missing or invalid
- Agent Auth Code missing/expired/already consumed
- `account.read` absent
- `trade.write` present
- restricted manifest exposes a forbidden write/money-movement tool
- token refresh fails
- encrypted vault cannot be decrypted
- account balance or positions response is unparseable
- provider/adapter binding is stale
- workflow-run attestation does not match the current same-run probe

Do not weaken these rules to obtain GO.
