"""
Core Execution Engine.
Orchestrates Market Data, Strategies, Risk Manager, and Broker in an asynchronous loop.
"""

from __future__ import annotations
import logging
import time
from typing import Dict, List, Optional
from config.market_hours import MarketHours
from config.settings import settings
from core.events import EventType, bus
from core.exceptions import RiskBreachError
from core.models import Candle, Order, Position, Signal, Tick
from broker.base import BaseBroker
from risk.risk_manager import RiskManager
from strategies.base_strategy import BaseStrategy

logger = logging.getLogger("ExecutionEngine")


class ExecutionEngine:
    def __init__(self, broker: BaseBroker, risk_manager: Optional[RiskManager] = None):
        self.broker = broker
        self.risk_manager = risk_manager or RiskManager()
        self.strategies: List[BaseStrategy] = []
        self.is_running: bool = False
        self.active_positions: Dict[str, Position] = {}
        self.trailing_stops: Dict[str, dict] = {}  # {symbol: {'peak': float, 'sl': float, 'trail_pct': 0.008}}

        # Subscribe to Event Bus
        bus.subscribe(EventType.TICK, self._handle_tick)
        bus.subscribe(EventType.CANDLE, self._handle_candle)
        bus.subscribe(EventType.RISK_BREACH, self._handle_risk_breach)

    def add_strategy(self, strategy: BaseStrategy) -> None:
        self.strategies.append(strategy)
        logger.info(f"Registered strategy: {strategy.name} for symbols: {strategy.symbols}")

    def start(self) -> None:
        """Start trading loop."""
        logger.info("Starting Algo Trading Engine...")
        self.broker.authenticate()
        self.is_running = True

        for strat in self.strategies:
            strat.on_start()

        logger.info(f"Engine running in {'PAPER' if settings.is_paper() else 'LIVE'} mode.")

    def stop(self) -> None:
        """Gracefully shut down trading engine."""
        logger.info("Stopping Algo Trading Engine...")
        self.is_running = False
        for strat in self.strategies:
            strat.on_stop()

    def process_signal(self, signal: Signal) -> Optional[Order]:
        """Validate signal through risk manager and route to broker."""
        positions = self.broker.get_positions()
        summary = self.broker.get_margins()

        try:
            # 1. Risk Manager validation
            self.risk_manager.validate_order(signal, positions, summary.net_pnl)

            # 2. Broker order routing
            order = self.broker.place_order(signal)
            self.risk_manager.record_trade_placed()

            # 3. Publish order event
            bus.publish(
                EventType.ORDER_FILLED,
                {
                    "order_id": order.order_id,
                    "symbol": order.symbol,
                    "type": order.transaction_type.value,
                    "qty": order.quantity,
                    "price": order.average_price,
                    "tag": order.tag,
                },
            )
            return order
        except RiskBreachError as re:
            logger.warning(f"Risk condition halted order: {re}")
            return None
        except Exception as e:
            logger.error(f"Failed to execute signal for {signal.symbol}: {e}")
            return None

    def _handle_tick(self, tick: Tick) -> None:
        if not self.is_running:
            return

        # Check for mandatory auto-square-off at 15:15 IST
        if MarketHours.is_past_square_off():
            self._execute_auto_square_off()
            return

        # Dynamic Trailing Profit & Stop Loss Adjustment
        self._check_trailing_stops(tick)

        # Process tick across strategies
        for strat in self.strategies:
            signal = strat.on_tick(tick)
            if signal:
                self.process_signal(signal)


    def _check_trailing_stops(self, tick: Tick) -> None:
        sym = tick.symbol
        ltp = tick.last_price
        if sym not in self.trailing_stops:
            return

        state = self.trailing_stops[sym]
        trail_pct = state.get("trail_pct", 0.008)
        pos = state.get("position")

        if not pos or pos.quantity == 0:
            del self.trailing_stops[sym]
            return

        # If price makes a new high, ratchet up the trailing stop
        if ltp > state["peak"]:
            state["peak"] = ltp
            new_sl = round(ltp * (1 - trail_pct), 2)
            if new_sl > state["sl"]:
                old_sl = state["sl"]
                state["sl"] = new_sl
                if new_sl > pos.average_price:
                    locked = round((new_sl - pos.average_price) * pos.quantity, 2)
                    logger.info(f"📈 [TRAILING PROFIT] Ratcheted SL for {sym} to Rs. {new_sl} (Locked Profit: Rs. {locked})")

        # Check if price pulls back to or below trailing stop
        if ltp <= state["sl"]:
            logger.info(f"🎯 [TRAILING SL TRIGGERED] Exiting {sym} @ Rs. {ltp} to lock in profit / cap risk.")
            exit_signal = Signal(
                symbol=sym,
                transaction_type=TransactionType.SELL if pos.quantity > 0 else TransactionType.BUY,
                order_type=OrderType.MARKET,
                product=pos.product,
                quantity=abs(pos.quantity),
                tag="TRAILING_SL_EXIT"
            )
            self.process_signal(exit_signal)
            if sym in self.trailing_stops:
                del self.trailing_stops[sym]

    def _handle_candle(self, data: dict) -> None:
        if not self.is_running:
            return

        candle: Candle = data["candle"]
        token: int = data["token"]

        for strat in self.strategies:
            for symbol in strat.symbols:
                signal = strat.on_candle(candle, symbol)
                if signal:
                    self.process_signal(signal)

    def _handle_risk_breach(self, data: dict) -> None:
        logger.critical("Risk breach received! Squaring off positions immediately.")
        self.emergency_square_off()

    def emergency_square_off(self) -> None:
        """Emergency circuit breaker exit."""
        logger.warning("Triggering EMERGENCY SQUARE OFF of all open positions!")
        self.broker.square_off_all()
        self.stop()

    def _execute_auto_square_off(self) -> None:
        logger.info("15:15 PM IST reached. Executing mandatory intraday auto-square-off...")
        self.broker.square_off_all()
        self.stop()
