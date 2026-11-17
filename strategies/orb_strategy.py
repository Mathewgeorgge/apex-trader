"""
Opening Range Breakout (ORB) with VWAP Strategy.
Captures the initial 15-minute range (9:15 AM - 9:30 AM IST) and trades high-volume breakouts.
"""

from __future__ import annotations
import logging
from datetime import time
from typing import Dict, List, Optional
from core.models import Candle, OrderType, ProductType, Signal, Tick, TransactionType
from data.instruments import instrument_manager
from strategies.base_strategy import BaseStrategy
from strategies.indicators import calculate_vwap, candles_to_dataframe

logger = logging.getLogger("ORBStrategy")


class ORBStrategy(BaseStrategy):
    def __init__(self, symbols: List[str], orb_minutes: int = 15, target_multiplier: float = 1.5):
        super().__init__(name="ORB_VWAP", symbols=symbols, timeframe_minutes=5)
        self.orb_minutes = orb_minutes
        self.target_multiplier = target_multiplier
        self.range_high: Dict[str, Optional[float]] = {s: None for s in symbols}
        self.range_low: Dict[str, Optional[float]] = {s: None for s in symbols}
        self.traded_today: Dict[str, bool] = {s: False for s in symbols}

    def on_tick(self, tick: Tick) -> Optional[Signal]:
        return None

    def on_candle(self, candle: Candle, symbol: str) -> Optional[Signal]:
        self.add_candle(symbol, candle)
        c_time = candle.timestamp.time()

        # Phase 1: During first 15 mins (9:15 to 9:30 AM IST), track Range High & Low
        if time(9, 15) <= c_time < time(9, 30):
            if self.range_high[symbol] is None or candle.high > self.range_high[symbol]:
                self.range_high[symbol] = candle.high
            if self.range_low[symbol] is None or candle.low < self.range_low[symbol]:
                self.range_low[symbol] = candle.low
            return None

        # Phase 2: After 9:30 AM, look for breakout if not yet traded today
        if c_time >= time(9, 30) and not self.traded_today[symbol]:
            high_level = self.range_high[symbol]
            low_level = self.range_low[symbol]

            if high_level is None or low_level is None:
                return None

            candles = self.candles[symbol]
            df = candles_to_dataframe(candles)
            vwap = calculate_vwap(df)
            curr_vwap = vwap.iloc[-1] if not vwap.empty else candle.close
            curr_close = candle.close
            range_span = high_level - low_level

            inst = instrument_manager.get_by_symbol(symbol)
            token = inst.instrument_token if inst else 0
            lot_size = inst.lot_size if inst else 1

            # Bullish Breakout: Candle closes above 15-min High & above VWAP
            if curr_close > high_level and curr_close > curr_vwap:
                stop_loss = round(high_level - (range_span * 0.5), 2)
                target = round(curr_close + (range_span * self.target_multiplier), 2)
                self.traded_today[symbol] = True

                logger.info(f"[{self.name}] ORB High Breakout: BUY {symbol} @ Rs. {curr_close:.2f} (Target: {target}, SL: {stop_loss})")
                return Signal(
                    strategy_name=self.name,
                    symbol=symbol,
                    instrument_token=token,
                    transaction_type=TransactionType.BUY,
                    order_type=OrderType.MARKET,
                    quantity=lot_size,
                    price=curr_close,
                    stop_loss=stop_loss,
                    target=target,
                    product=ProductType.MIS,
                    tag="ORB_BUY",
                )

            # Bearish Breakdown: Candle closes below 15-min Low & below VWAP
            elif curr_close < low_level and curr_close < curr_vwap:
                stop_loss = round(low_level + (range_span * 0.5), 2)
                target = round(curr_close - (range_span * self.target_multiplier), 2)
                self.traded_today[symbol] = True

                logger.info(f"[{self.name}] ORB Low Breakdown: SELL {symbol} @ Rs. {curr_close:.2f} (Target: {target}, SL: {stop_loss})")
                return Signal(
                    strategy_name=self.name,
                    symbol=symbol,
                    instrument_token=token,
                    transaction_type=TransactionType.SELL,
                    order_type=OrderType.MARKET,
                    quantity=lot_size,
                    price=curr_close,
                    stop_loss=stop_loss,
                    target=target,
                    product=ProductType.MIS,
                    tag="ORB_SELL",
                )

        return None
