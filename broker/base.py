"""
Abstract Base Class for Broker Integrations.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional
from core.models import AccountSummary, Candle, Order, Position, Signal


class BaseBroker(ABC):
    @abstractmethod
    def authenticate(self) -> bool:
        """Authenticate with the broker API and establish session."""
        pass

    @abstractmethod
    def get_profile(self) -> Dict[str, Any]:
        """Fetch trader profile and account details."""
        pass

    @abstractmethod
    def get_margins(self) -> AccountSummary:
        """Fetch cash, collateral, and used margins."""
        pass

    @abstractmethod
    def get_orders(self) -> List[Order]:
        """Fetch all orders placed today."""
        pass

    @abstractmethod
    def get_positions(self) -> List[Position]:
        """Fetch all active and closed positions for the day."""
        pass

    @abstractmethod
    def place_order(self, signal: Signal) -> Order:
        """Submit a new order to the broker or paper engine."""
        pass

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order."""
        pass

    @abstractmethod
    def modify_order(
        self,
        order_id: str,
        price: Optional[float] = None,
        trigger_price: Optional[float] = None,
        quantity: Optional[int] = None,
    ) -> bool:
        """Modify price or quantity of an open order."""
        pass

    @abstractmethod
    def get_quote(self, symbol: str, exchange: str = "NSE") -> Dict[str, Any]:
        """Fetch real-time snapshot quote for an instrument."""
        pass

    @abstractmethod
    def get_historical_data(
        self,
        instrument_token: int,
        from_date: datetime,
        to_date: datetime,
        interval: str = "minute",
    ) -> List[Candle]:
        """Fetch historical candle bars (OHLCV)."""
        pass

    @abstractmethod
    def square_off_all(self) -> List[Order]:
        """Emergency kill-switch: square off all open positions immediately."""
        pass
