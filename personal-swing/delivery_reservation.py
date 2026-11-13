"""Plan and verify one-shot request intent. No network, send, or device ACK.

The caller must independently verify current source/score eligibility and
serialize against nonparticipating writers (including row moves). Every
participating writer uses the same durable per-key Google Sheets named-range ID.
This is a unique insert, not a general compare-and-swap on Sheet cell values.
"""
from dataclasses import dataclass
from datetime import date, datetime
import hashlib
import json
import re
import sys

from alert_ledger_contract import CONFIRMED_PENDING, REQUESTED, parse_ledger


DIGEST_HEADER = (
    "KAYIT_KIMLIGI", "ASOF_ET", "EPIZOT_KIMLIGI", "SEMBOL", "KAYIT_TIPI",
    "SIRA", "SKOR_100", "TREND_20", "RSI_15", "RVOL_15", "REL_GUC_15",
    "LIKIDITE_10", "RISK_15", "FIYAT_YAPISI_10", "GUNCEL_IEX_CLOSE_USD",
    "ORIJINAL_REFERANS_USD", "ORIJINAL_STOP_USD", "ORIJINAL_HEDEF_2R_USD",
    "TEORIK_DEGISIM_YUZDE", "STOPA_MESAFE_YUZDE", "HEDEFE_MESAFE_YUZDE",
    "TAKIP_SEANSI", "RSI14", "RVOL20", "20SEANS_GETIRI_YUZDE", "RISK_NOTU",
    "KANIT_URL", "BILDIRIM_DURUMU", "BILDIRIM_ZAMANI_TR", "KAYIT_SHA256",
    "KAPSAM_SHA256", "ALGORITMA_SHA256", "SKOR_SURUMU",
    "ORT_IEX_DOLAR_HACMI", "ATR_RISK_YUZDE",
)
DIGEST_READY = "READY_FOR_CHATGPT_DAILY_DIGEST"
DIGEST_REQUESTED = "REQUESTED_NOT_DEVICE_ACK"
SHA = re.compile(r"[a-f0-9]{64}")
STAMP = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2} TRT")


class Refused(ValueError):
    pass


def need(ok, reason):
    if not ok:
        raise Refused(reason)


def validate_context(sheet_id, asof, stamp):
    need(type(sheet_id) is int and 0 <= sheet_id <= 2147483647, "BAD_SHEET_ID")
    need(type(asof) is str and type(stamp) is str and STAMP.fullmatch(stamp),
         "BAD_RESERVATION_CONTEXT")
    try:
        d = date.fromisoformat(asof)
        local = datetime.strptime(stamp, "%Y-%m-%d %H:%M TRT")
    except ValueError:
        raise Refused("BAD_RESERVATION_CONTEXT") from None
    need(d.isoformat() == asof and local.date() >= d, "BAD_RESERVATION_CONTEXT")


def matrix(values, width):
    need(type(values) is list and values and len(values) <= 50001,
         "MISSING_OR_OVERSIZED_MATRIX")
    out = []
    for row in values:
        need(type(row) is list and len(row) <= width and
             all(type(v) is str for v in row), "BAD_MATRIX_SHAPE")
        out.append(tuple(row) + ("",) * (width - len(row)))
    return tuple(out)


@dataclass(frozen=True)
class Plan:
    kind: str
    sheet_id: int
    width: int
    status_col: int
    target_status: str
    stamp: str
    baseline: tuple
    targets: tuple

    def requests(self):
        requests = []
        for key, row in self.targets:
            # No raw symbol or private row content enters marker identifiers.
            digest = hashlib.sha256(
                f"XRAY_PERSONAL_DELIVERY_V1\n{self.kind}\n{key}".encode("ascii")
            ).hexdigest()
            bounds = dict(sheetId=self.sheet_id, startRowIndex=row,
                          endRowIndex=row + 1, startColumnIndex=self.status_col,
                          endColumnIndex=self.status_col + 2)
            requests.append({"addNamedRange": {"namedRange": {
                "namedRangeId": "xray_" + digest,
                "name": "XRAY_DELIVERY_" + digest,
                "range": bounds,
            }}})
            requests.append({"updateCells": {
                "start": {"sheetId": self.sheet_id, "rowIndex": row,
                          "columnIndex": self.status_col},
                "rows": [{"values": [
                    {"userEnteredValue": {"stringValue": self.target_status}},
                    {"userEnteredValue": {"stringValue": self.stamp}},
                ]}],
                "fields": "userEnteredValue",
            }})
        return requests


def plan_events(sheet_id, values, keys, asof, stamp):
    validate_context(sheet_id, asof, stamp)
    need(type(keys) in (tuple, list) and 0 < len(keys) <= 6 and
         all(type(k) is str for k in keys) and len(set(keys)) == len(keys),
         "BAD_EVENT_KEYS")
    before = matrix(values, 20)
    try:
        entries = parse_ledger(values)
    except ValueError:
        raise Refused("EVENT_LEDGER_INVALID") from None
    targets = []
    for key in keys:
        need(key in entries, "EVENT_MISSING")
        row = entries[key]["row_index"] - 1
        fields = before[row]
        need(fields[4] == asof and fields[17:19] == (CONFIRMED_PENDING, ""),
             "EVENT_NOT_CURRENT_PENDING")
        targets.append((key, row))
    return Plan("event", sheet_id, 20, 17, REQUESTED, stamp, before, tuple(targets))


def plan_digest(sheet_id, values, asof, verified_sha, stamp):
    validate_context(sheet_id, asof, stamp)
    need(type(verified_sha) is str and SHA.fullmatch(verified_sha), "BAD_VERIFIED_SHA")
    before = matrix(values, 35)
    need(before[0] == DIGEST_HEADER, "DIGEST_HEADER_DRIFT")
    key = asof + "|SUMMARY"
    matches = [(i, r) for i, r in enumerate(before[1:], 1)
               if r[0] == key or (r[1] == asof and r[4] == "SUMMARY")]
    need(len(matches) == 1, "DIGEST_IDENTITY_NOT_UNIQUE")
    row, fields = matches[0]
    need(fields[0] == key and fields[1] == asof and fields[4] == "SUMMARY"
         and fields[27:30] == (DIGEST_READY, "", verified_sha), "DIGEST_NOT_CURRENT_READY")
    return Plan("digest", sheet_id, 35, 27, DIGEST_REQUESTED, stamp, before, ((key, row),))


def verify_commit(plan, response, observed, spreadsheet_id):
    """Require the successful POST's own receipt and a fresh full GET.

    Lost/uncertain POST replies must HOLD even if a later GET matches. Never
    retry, delete the marker, or reset a row to PENDING to force a send.
    """
    need(type(spreadsheet_id) is str and bool(spreadsheet_id) and
         type(response) is dict and response.get("spreadsheetId") == spreadsheet_id,
         "POST_RECEIPT_UNKNOWN")
    replies = response.get("replies")
    requests = plan.requests()
    need(type(replies) is list and len(replies) == len(requests), "POST_RECEIPT_UNKNOWN")
    for i in range(0, len(requests), 2):
        expected = requests[i]
        need(replies[i] == expected and replies[i + 1] == {}, "POST_RECEIPT_DRIFT")
    expected_rows = list(plan.baseline)
    for _, row in plan.targets:
        col = plan.status_col
        r = expected_rows[row]
        expected_rows[row] = r[:col] + (plan.target_status, plan.stamp) + r[col + 2:]
    need(tuple(expected_rows) == matrix(observed, plan.width), "READBACK_DRIFT")
    return {"reserved": len(plan.targets), "message_proven": False, "device_ack": False}


def main():
    """Private caller only. Reads JSON stdin and writes JSON stdout, no network."""
    try:
        item = json.load(sys.stdin)
        need(type(item) is dict, "BAD_INPUT")
        args = item["sheet_id"], item["baseline"]
        time_args = item["asof"], item["stamp"]
        if item["kind"] == "event":
            plan = plan_events(*args, item["keys"], *time_args)
        elif item["kind"] == "digest":
            plan = plan_digest(*args, time_args[0], item["verified_sha"], time_args[1])
        else:
            raise Refused("BAD_KIND")
        if item["action"] == "plan":
            out = {"status": "PLAN_ONLY", "requests": plan.requests()}
        elif item["action"] == "verify":
            out = verify_commit(plan, item["response"], item["observed"], item["spreadsheet_id"])
        else:
            raise Refused("BAD_ACTION")
        print(json.dumps(out, sort_keys=True))
        return 0
    except (ValueError, KeyError, TypeError, OverflowError):
        print(json.dumps({"status": "RESERVATION_HOLD", "message_proven": False,
                          "device_ack": False}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
