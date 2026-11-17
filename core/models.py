"""
Core Domain Models and Data Structures for Indian Algo Trading.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional


class Exchange(str, Enum):
    NSE = "NSE"
    NFO = "NFO"
    BSE = "BSE"
    MCX = "MCX"


class TransactionType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    SL = "SL"        # Stop-loss limit
    SL_M = "SL-M"    # Stop-loss market


class ProductType(str, Enum):
    MIS = "MIS"      # Margin Intraday Square-off
    CNC = "CNC"      # Cash and Carry (Delivery)
    NRML = "NRML"    # Normal (F&O Over-the-counter / overnight)


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    OPEN = "OPEN"
    COMPLETE = "COMPLETE"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


@dataclass
class Instrument:
    instrument_token: int
    tradingsymbol: str
    exchange: str = "NSE"
    name: str = ""
    lot_size: int = 1
    tick_size: float = 0.05
    instrument_type: str = "EQ"
    expiry: Optional[datetime] = None
    strike: Optional[float] = None


@dataclass
class Tick:
    instrument_token: int
    last_price: float
    volume: int = 0
    change: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    oi: Optional[int] = None
    depth: Optional[Dict[str, Any]] = None


@dataclass
class Candle:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int = 0


@dataclass
class Signal:
    strategy_name: str
    symbol: str
    instrument_token: int
    transaction_type: TransactionType
    order_type: OrderType
    quantity: int
    price: float = 0.0
    stop_loss: Optional[float] = None
    target: Optional[float] = None
    trailing_sl: Optional[float] = None
    product: ProductType = ProductType.MIS
    timestamp: datetime = field(default_factory=datetime.now)
    tag: str = ""


@dataclass
class Order:
    order_id: str
    symbol: str
    instrument_token: int
    transaction_type: TransactionType
    order_type: OrderType
    product: ProductType
    quantity: int
    filled_quantity: int = 0
    price: float = 0.0
    trigger_price: float = 0.0
    average_price: float = 0.0
    status: OrderStatus = OrderStatus.PENDING
    rejection_reason: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    tag: str = ""


@dataclass
class Position:
    symbol: str
    instrument_token: int
    product: ProductType
    quantity: int = 0          # Positive = Long, Negative = Short, 0 = Flat
    buy_price: float = 0.0
    sell_price: float = 0.0
    average_price: float = 0.0
    ltp: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0

    @property
    def total_pnl(self) -> float:
        return self.realized_pnl + self.unrealized_pnl

    def update_ltp(self, price: float) -> None:
        self.ltp = price
        if self.quantity > 0:
            self.unrealized_pnl = (price - self.average_price) * self.quantity
        elif self.quantity < 0:
            self.unrealized_pnl = (self.average_price - price) * abs(self.quantity)
        else:
            self.unrealized_pnl = 0.0


@dataclass
class AccountSummary:
    available_cash: float = 0.0
    collateral: float = 0.0
    margin_used: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0

    @property
    def total_margin(self) -> float:
        return self.available_cash + self.collateral

    @property
    def net_pnl(self) -> float:
        return self.realized_pnl + self.unrealized_pnl
