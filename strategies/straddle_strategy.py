"""
9:20 AM Index Options Short Straddle Strategy.
A premier options selling strategy in Indian markets capturing intraday theta decay.
"""

from __future__ import annotations
import logging
from datetime import time
from typing import Dict, List, Optional
from core.models import Candle, OrderType, ProductType, Signal, Tick, TransactionType
from data.instruments import instrument_manager
from strategies.base_strategy import BaseStrategy

logger = logging.getLogger("ShortStraddleStrategy")


class ShortStraddleStrategy(BaseStrategy):
    def __init__(
        self,
        index_symbol: str = "NIFTY 50",
        strike_step: int = 50,
        stop_loss_pct: float = 0.25,  # 25% stop-loss per leg
        entry_time: time = time(9, 20),
        exit_time: time = time(15, 10),
    ):
        super().__init__(name="920_Short_Straddle", symbols=[index_symbol], timeframe_minutes=1)
        self.index_symbol = index_symbol
        self.strike_step = strike_step
        self.stop_loss_pct = stop_loss_pct
        self.entry_time = entry_time
        self.exit_time = exit_time
        self.executed_today: bool = False
        self.active_legs: Dict[str, dict] = {}

    def get_atm_strike(self, spot_price: float) -> int:
        """Rounds spot price to the nearest strike step (e.g. 50 for Nifty, 100 for Bank Nifty)."""
        return int(round(spot_price / self.strike_step) * self.strike_step)

    def on_tick(self, tick: Tick) -> Optional[Signal]:
        t_time = tick.timestamp.time()

        # Check for 9:20 AM trigger
        if not self.executed_today and t_time >= self.entry_time and t_time < time(9, 25):
            spot = tick.last_price
            atm_strike = self.get_atm_strike(spot)
            logger.info(f"[{self.name}] 9:20 AM triggered! Spot: {spot:.2f}, ATM Strike: {atm_strike}")
            self.executed_today = True

            # In live options trading, instrument tokens for CE & PE would be selected from instrument master
            # For demonstration, we simulate generating the short straddle pair signals
            ce_symbol = f"{self.index_symbol}_{atm_strike}_CE"
            pe_symbol = f"{self.index_symbol}_{atm_strike}_PE"

            # Create ATM Call Sell Signal
            ce_signal = Signal(
                strategy_name=self.name,
                symbol=ce_symbol,
                instrument_token=tick.instrument_token,
                transaction_type=TransactionType.SELL,
                order_type=OrderType.MARKET,
                quantity=25,  # Standard Nifty lot size
                price=tick.last_price,
                stop_loss=tick.last_price * (1 + self.stop_loss_pct),
                product=ProductType.MIS,
                tag="STRADDLE_CE",
            )
            return ce_signal

        return None

    def on_candle(self, candle: Candle, symbol: str) -> Optional[Signal]:
        return None
