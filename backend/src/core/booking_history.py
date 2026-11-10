"""Helpers for selecting the active booking store from payment history."""

from __future__ import annotations

from typing import Any, Dict, Iterable


def is_booking_store(store_info: Dict[str, Any]) -> bool:
    supply_types = store_info.get("supplyTypes") or []
    return store_info.get("supplyType") == 6 or any(
        supply.get("code") == "BOOKING" for supply in supply_types
    )


def booking_store_id_from_history(histories: Iterable[Dict[str, Any]]) -> str | None:
    """Return the store of the newest confirmed booking payment.

    Pointbook is returned newest-first.  A canceled booking-store entry is kept
    only as a fallback when no confirmed entry exists.
    """
    canceled_store_id = None
    for history in histories:
        store_info = history.get("storeInfo") or {}
        store_id = store_info.get("storeId")
        if not is_booking_store(store_info) or not store_id:
            continue
        if history.get("state") == "CONFIRM":
            return str(store_id)
        if history.get("state") == "CANCELED" and canceled_store_id is None:
            canceled_store_id = str(store_id)
    return canceled_store_id


def active_booking_menu_histories(
    histories: Iterable[Dict[str, Any]], store_id: str
) -> Dict[str, Dict[str, Any]]:
    """Map active menu IDs to their newest CONFIRM pointbook entry."""
    resolved_menu_ids = set()
    active: Dict[str, Dict[str, Any]] = {}
    for history in histories:
        store_info = history.get("storeInfo") or {}
        if store_info.get("storeId") != store_id or not is_booking_store(store_info):
            continue
        for menu in store_info.get("orderedMenus") or []:
            menu_id = str(menu.get("menuId") or "")
            if not menu_id or menu_id in resolved_menu_ids:
                continue
            resolved_menu_ids.add(menu_id)
            if history.get("state") == "CONFIRM":
                active[menu_id] = history
    return active
