"""
Abstract Base Strategy Framework.
Provides candle caching, state management, and signal generation hooks.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from core.models import Candle, Order, Signal, Tick


class BaseStrategy(ABC):
    def __init__(self, name: str, symbols: List[str], timeframe_minutes: int = 5):
        self.name = name
        self.symbols = symbols
        self.timeframe_minutes = timeframe_minutes
        self.candles: Dict[str, List[Candle]] = {sym: [] for sym in symbols}
        self.active_signals: List[Signal] = []
        self.is_running: bool = False

    def on_start(self) -> None:
        """Called when strategy starts executing."""
        self.is_running = True

    def on_stop(self) -> None:
        """Called when strategy stops."""
        self.is_running = False

    def add_candle(self, symbol: str, candle: Candle) -> None:
        """Store historical candles, keeping max window of 300 candles."""
        if symbol not in self.candles:
            self.candles[symbol] = []
        self.candles[symbol].append(candle)
        if len(self.candles[symbol]) > 300:
            self.candles[symbol].pop(0)

    @abstractmethod
    def on_tick(self, tick: Tick) -> Optional[Signal]:
        """Process incoming live tick."""
        pass

    @abstractmethod
    def on_candle(self, candle: Candle, symbol: str) -> Optional[Signal]:
        """Process closed candle bar."""
        pass

    def on_order_update(self, order: Order) -> None:
        """Called when an order status updates."""
        pass
