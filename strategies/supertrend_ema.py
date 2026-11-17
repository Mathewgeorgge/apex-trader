"""
Supertrend + EMA Trend Following Strategy for Indian Equities and Index Futures.
Combines Supertrend (10, 3) with a 20-period EMA filter for trend confirmation.
"""

from __future__ import annotations
import logging
from typing import List, Optional
from core.models import Candle, OrderType, ProductType, Signal, Tick, TransactionType
from data.instruments import instrument_manager
from strategies.base_strategy import BaseStrategy
from strategies.indicators import (
    calculate_ema,
    calculate_supertrend,
    candles_to_dataframe,
)

logger = logging.getLogger("SupertrendEMAStrategy")


class SupertrendEMAStrategy(BaseStrategy):
    def __init__(
        self,
        symbols: List[str],
        timeframe_minutes: int = 5,
        st_period: int = 10,
        st_multiplier: float = 3.0,
        ema_period: int = 20,
        risk_reward_ratio: float = 2.0,
    ):
        super().__init__(name="Supertrend_EMA", symbols=symbols, timeframe_minutes=timeframe_minutes)
        self.st_period = st_period
        self.st_multiplier = st_multiplier
        self.ema_period = ema_period
        self.risk_reward_ratio = risk_reward_ratio
        self.in_position = {s: 0 for s in symbols}  # 1 = Long, -1 = Short, 0 = Flat

    def on_tick(self, tick: Tick) -> Optional[Signal]:
        # Indicators are evaluated on candle close
        return None

    def on_candle(self, candle: Candle, symbol: str) -> Optional[Signal]:
        self.add_candle(symbol, candle)
        candles = self.candles[symbol]

        if len(candles) < max(self.st_period, self.ema_period) + 5:
            return None

        df = candles_to_dataframe(candles)
        st_line, st_dir = calculate_supertrend(df, period=self.st_period, multiplier=self.st_multiplier)
        ema = calculate_ema(df["close"], period=self.ema_period)

        curr_close = df["close"].iloc[-1]
        curr_dir = st_dir.iloc[-1]
        prev_dir = st_dir.iloc[-2]
        curr_ema = ema.iloc[-1]
        curr_st = st_line.iloc[-1]

        inst = instrument_manager.get_by_symbol(symbol)
        token = inst.instrument_token if inst else 0
        lot_size = inst.lot_size if inst else 1

        # Bullish signal: Supertrend flipped to Green (1) and Close > 20 EMA
        if prev_dir == -1 and curr_dir == 1 and curr_close > curr_ema:
            if self.in_position[symbol] <= 0:
                stop_loss = round(curr_st, 2)
                risk = curr_close - stop_loss
                target = round(curr_close + (risk * self.risk_reward_ratio), 2)

                self.in_position[symbol] = 1
                logger.info(f"[{self.name}] BUY Signal generated for {symbol} @ Rs. {curr_close:.2f} (SL: {stop_loss}, Target: {target})")
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
                    tag="ST_EMA_BUY",
                )

        # Bearish signal: Supertrend flipped to Red (-1) and Close < 20 EMA
        elif prev_dir == 1 and curr_dir == -1 and curr_close < curr_ema:
            if self.in_position[symbol] >= 0:
                stop_loss = round(curr_st, 2)
                risk = stop_loss - curr_close
                target = round(curr_close - (risk * self.risk_reward_ratio), 2)

                self.in_position[symbol] = -1
                logger.info(f"[{self.name}] SELL Signal generated for {symbol} @ Rs. {curr_close:.2f} (SL: {stop_loss}, Target: {target})")
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
                    tag="ST_EMA_SELL",
                )

        return None
