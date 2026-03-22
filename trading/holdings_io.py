from __future__ import annotations

import json
from pathlib import Path

from trading.schemas import PortfolioState, Position


def save_holdings_snapshot(path: str | Path, *, as_of_date: str, state: PortfolioState) -> None:
    snapshot_path = Path(path)
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "as_of_date": as_of_date,
        "state": state.to_dict(),
    }
    snapshot_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_holdings_snapshot(path: str | Path) -> dict:
    snapshot_path = Path(path)
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    state_payload = payload.get("state", {})
    positions = [
        Position(
            code=position_payload["code"],
            entry_date=position_payload["entry_date"],
            entry_price=position_payload["entry_price"],
            weight=position_payload["weight"],
            quantity=position_payload.get("quantity", 100),
        )
        for position_payload in state_payload.get("positions", [])
    ]
    state = PortfolioState(
        cash=state_payload.get("cash", 0.0),
        positions=positions,
    )
    return {
        "as_of_date": payload["as_of_date"],
        "state": state,
    }
