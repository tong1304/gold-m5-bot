from __future__ import annotations

from typing import Any


_SENT_KEYS: set[tuple[str, str]] = set()
_INSTALLED = False


def _text(value: Any) -> str:
    return str(value or "").upper().strip()


def _alert(result: Any) -> dict[str, Any]:
    risk = getattr(result, "risk", {}) or {}
    value = risk.get("trade_alert") if isinstance(risk, dict) else None
    return dict(value) if isinstance(value, dict) else {}


def _key(result: Any, alert: dict[str, Any]) -> tuple[str, str] | None:
    symbol = _text(getattr(result, "symbol", None) or alert.get("symbol"))
    opportunity_id = str(alert.get("opportunity_id") or "").strip()
    if not symbol or not opportunity_id:
        return None
    return symbol, opportunity_id


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    from . import service as service_module

    original = service_module.send_decision

    def guarded_send_decision(result: Any, *args: Any, **kwargs: Any) -> Any:
        alert = _alert(result)
        authorized = (
            alert.get("state") == "TRADE_ALERT"
            and alert.get("user_action") == "USER_ACTION_REQUIRED"
            and alert.get("alert_authorized_by") == "E9"
            and alert.get("broker_execution") is False
            and alert.get("position_open") is False
        )
        key = _key(result, alert)
        if not authorized or key is None:
            print(
                f"[PRODUCTION V2] ALERT_DELIVERY action=SKIP reason=UNAUTHORIZED_OR_MISSING_ID "
                f"state={alert.get('state','NONE')} opportunity_id={alert.get('opportunity_id') or 'NONE'}",
                flush=True,
            )
            return None
        if key in _SENT_KEYS:
            print(
                f"[PRODUCTION V2] ALERT_DELIVERY action=SKIP reason=DUPLICATE "
                f"symbol={key[0]} opportunity_id={key[1]}",
                flush=True,
            )
            return None
        response = original(result, *args, **kwargs)
        _SENT_KEYS.add(key)
        print(
            f"[PRODUCTION V2] ALERT_DELIVERY action=SENT symbol={key[0]} "
            f"direction={alert.get('direction')} opportunity_id={key[1]} "
            f"user_action=USER_ACTION_REQUIRED broker_execution=False position_open=False",
            flush=True,
        )
        return response

    service_module.send_decision = guarded_send_decision
    _INSTALLED = True
    print("[PRODUCTION V2] ALERT_DELIVERY_BOUNDARY installed=TRUE mode=MANUAL_EXECUTION dedup=OPPORTUNITY_ID", flush=True)


def reset_for_tests() -> None:
    _SENT_KEYS.clear()
