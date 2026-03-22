from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Position:
    code: str
    entry_date: str
    entry_price: float
    weight: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Order:
    code: str
    side: str
    quantity: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TradeFill:
    code: str
    side: str
    quantity: int
    fill_price: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RiskState:
    mode: str
    allow_new_entries: bool
    max_total_exposure: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class BacktestDailySnapshot:
    date: str
    cash: float
    position_count: int
    benchmark_return: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PortfolioState:
    cash: float
    positions: list[Position] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "cash": self.cash,
            "positions": [position.to_dict() for position in self.positions],
        }
