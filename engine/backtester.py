"""
Historical Strategy Backtester & Performance Analyzer.
Evaluates strategy performance, win rate, Sharpe ratio, and maximum drawdown.
"""

from __future__ import annotations
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional
import numpy as np
import pandas as pd
from core.models import Candle, OrderType, Signal, TransactionType
from strategies.base_strategy import BaseStrategy

logger = logging.getLogger("Backtester")


@dataclass
class BacktestTrade:
    entry_time: datetime
    exit_time: datetime
    symbol: str
    direction: str
    quantity: int
    entry_price: float
    exit_price: float
    pnl: float
    return_pct: float
    exit_reason: str


@dataclass
class BacktestMetrics:
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate_pct: float = 0.0
    total_pnl: float = 0.0
    profit_factor: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    average_trade_pnl: float = 0.0


class Backtester:
    def __init__(self, strategy: BaseStrategy, initial_capital: float = 100000.0, slippage_pct: float = 0.0005):
        self.strategy = strategy
        self.initial_capital = initial_capital
        self.slippage_pct = slippage_pct
        self.trades: List[BacktestTrade] = []

    def run(self, symbol: str, candles: List[Candle]) -> BacktestMetrics:
        """Run strategy over chronological candle history."""
        self.trades.clear()
        position: Optional[Signal] = None
        entry_price: float = 0.0
        entry_time: Optional[datetime] = None

        for candle in candles:
            # 1. Check existing position exit conditions (SL or Target hit)
            if position is not None:
                is_long = position.transaction_type == TransactionType.BUY
                exit_price = None
                exit_reason = None

                if is_long:
                    if position.stop_loss and candle.low <= position.stop_loss:
                        exit_price = position.stop_loss * (1 - self.slippage_pct)
                        exit_reason = "STOP_LOSS"
                    elif position.target and candle.high >= position.target:
                        exit_price = position.target * (1 - self.slippage_pct)
                        exit_reason = "TARGET"
                else:
                    if position.stop_loss and candle.high >= position.stop_loss:
                        exit_price = position.stop_loss * (1 + self.slippage_pct)
                        exit_reason = "STOP_LOSS"
                    elif position.target and candle.low <= position.target:
                        exit_price = position.target * (1 + self.slippage_pct)
                        exit_reason = "TARGET"

                if exit_price and exit_reason:
                    pnl = (exit_price - entry_price) * position.quantity if is_long else (entry_price - exit_price) * position.quantity
                    ret_pct = ((exit_price - entry_price) / entry_price) * 100 if is_long else ((entry_price - exit_price) / entry_price) * 100

                    trade = BacktestTrade(
                        entry_time=entry_time or candle.timestamp,
                        exit_time=candle.timestamp,
                        symbol=symbol,
                        direction="BUY" if is_long else "SELL",
                        quantity=position.quantity,
                        entry_price=round(entry_price, 2),
                        exit_price=round(exit_price, 2),
                        pnl=round(pnl, 2),
                        return_pct=round(ret_pct, 2),
                        exit_reason=exit_reason,
                    )
                    self.trades.append(trade)
                    position = None

            # 2. Feed candle to strategy to evaluate new signals
            signal = self.strategy.on_candle(candle, symbol)
            if signal and position is None:
                position = signal
                is_buy = signal.transaction_type == TransactionType.BUY
                entry_price = candle.close * (1 + self.slippage_pct if is_buy else 1 - self.slippage_pct)
                entry_time = candle.timestamp

        return self.compute_metrics()

    def compute_metrics(self) -> BacktestMetrics:
        if not self.trades:
            return BacktestMetrics()

        pnls = [t.pnl for t in self.trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]

        total_trades = len(pnls)
        win_count = len(wins)
        loss_count = len(losses)
        win_rate = (win_count / total_trades) * 100 if total_trades > 0 else 0.0

        total_pnl = sum(pnls)
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else 999.0

        # Calculate equity curve & Max Drawdown
        equity_curve = np.cumsum([self.initial_capital] + pnls)
        peak = np.maximum.accumulate(equity_curve)
        drawdowns = (peak - equity_curve) / peak
        max_dd = float(np.max(drawdowns)) * 100

        # Sharpe ratio
        returns = np.array(pnls) / self.initial_capital
        std = np.std(returns)
        sharpe = float((np.mean(returns) / std) * np.sqrt(252)) if std > 0 else 0.0

        return BacktestMetrics(
            total_trades=total_trades,
            winning_trades=win_count,
            losing_trades=loss_count,
            win_rate_pct=round(win_rate, 2),
            total_pnl=round(total_pnl, 2),
            profit_factor=profit_factor,
            max_drawdown_pct=round(max_dd, 2),
            sharpe_ratio=round(sharpe, 2),
            average_trade_pnl=round(float(np.mean(pnls)), 2),
        )
