"""
Unit and Integration Tests for Zerodha Algo Trader.
"""

from __future__ import annotations
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import unittest
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from broker.paper_broker import PaperBroker
from core.events import EventBus, EventType
from core.exceptions import RiskBreachError
from core.models import Candle, OrderType, Position, ProductType, Signal, TransactionType
from risk.risk_manager import RiskManager
from strategies.indicators import (
    calculate_atr,
    calculate_cpr,
    calculate_ema,
    calculate_supertrend,
    calculate_vwap,
    candles_to_dataframe,
)
from strategies.orb_strategy import ORBStrategy
from strategies.supertrend_ema import SupertrendEMAStrategy


class TestIndicators(unittest.TestCase):
    def setUp(self):
        # Generate 50 synthetic candle bars
        dates = [datetime(2026, 1, 1, 9, 15) + timedelta(minutes=5 * i) for i in range(50)]
        prices = 100.0 + np.cumsum(np.random.normal(0, 0.5, 50))
        self.candles = [
            Candle(
                timestamp=dates[i],
                open=prices[i] - 0.2,
                high=prices[i] + 0.5,
                low=prices[i] - 0.5,
                close=prices[i] + 0.1,
                volume=1000 + i * 50,
            )
            for i in range(50)
        ]
        self.df = candles_to_dataframe(self.candles)

    def test_dataframe_conversion(self):
        self.assertEqual(len(self.df), 50)
        self.assertIn("close", self.df.columns)
        self.assertIn("volume", self.df.columns)

    def test_ema_calculation(self):
        ema20 = calculate_ema(self.df["close"], 20)
        self.assertEqual(len(ema20), 50)
        self.assertFalse(np.isnan(ema20.iloc[-1]))

    def test_atr_and_supertrend(self):
        atr = calculate_atr(self.df, 10)
        self.assertTrue(atr.iloc[-1] > 0)
        st_line, st_dir = calculate_supertrend(self.df, period=10, multiplier=3.0)
        self.assertIn(st_dir.iloc[-1], [-1, 1])

    def test_vwap(self):
        vwap = calculate_vwap(self.df)
        self.assertTrue(vwap.iloc[-1] > 0)

    def test_cpr(self):
        cpr = calculate_cpr(high=25000.0, low=24800.0, close=24900.0)
        self.assertEqual(cpr["pivot"], 24900.0)
        self.assertTrue(cpr["tc"] >= cpr["bc"])


class TestRiskManager(unittest.TestCase):
    def setUp(self):
        self.risk = RiskManager(
            max_daily_loss=5000.0,
            max_capital_per_trade=50000.0,
            max_trades_per_day=5,
            max_open_positions=2,
        )

    def test_position_sizing(self):
        # Entry 1000, SL 980 -> Risk per share is 20
        # Risk capital: 5000 * 0.25 = 1250
        # Raw quantity: 1250 / 20 = 62
        # But max_capital_per_trade = 50000 -> max_allowed_qty = 50000 / 1000 = 50
        # Risk manager correctly caps qty at 50!
        qty_capped = self.risk.calculate_position_size(entry_price=1000.0, stop_loss_price=980.0)
        self.assertEqual(qty_capped, 50)

        # When capital is ample, sizing strictly follows risk per share
        self.risk.max_capital_per_trade = 200000.0
        qty_uncapped = self.risk.calculate_position_size(entry_price=1000.0, stop_loss_price=980.0)
        self.assertEqual(qty_uncapped, 62)

    def test_daily_loss_breach(self):
        signal = Signal(
            strategy_name="TEST",
            symbol="RELIANCE",
            instrument_token=738561,
            transaction_type=TransactionType.BUY,
            order_type=OrderType.MARKET,
            quantity=10,
            price=2500.0,
        )
        with self.assertRaises(RiskBreachError):
            self.risk.validate_order(signal, current_positions=[], net_pnl=-5500.0)
        self.assertTrue(self.risk.circuit_breaker_triggered)

    def test_max_trade_count(self):
        signal = Signal(
            strategy_name="TEST",
            symbol="INFY",
            instrument_token=408065,
            transaction_type=TransactionType.BUY,
            order_type=OrderType.MARKET,
            quantity=5,
            price=1500.0,
        )
        for _ in range(5):
            self.risk.record_trade_placed()

        with self.assertRaises(RiskBreachError):
            self.risk.validate_order(signal, current_positions=[], net_pnl=500.0)


class TestPaperBroker(unittest.TestCase):
    def setUp(self):
        self.broker = PaperBroker(initial_capital=100000.0)
        self.broker.update_quote("RELIANCE", 2500.0)

    def test_place_paper_order(self):
        signal = Signal(
            strategy_name="TEST_STRAT",
            symbol="RELIANCE",
            instrument_token=738561,
            transaction_type=TransactionType.BUY,
            order_type=OrderType.MARKET,
            quantity=10,
            price=2500.0,
        )
        order = self.broker.place_order(signal)
        self.assertEqual(len(self.broker.orders), 1)
        self.assertEqual(len(self.broker.get_positions()), 1)
        pos = self.broker.get_positions()[0]
        self.assertEqual(pos.symbol, "RELIANCE")
        self.assertEqual(pos.quantity, 10)

    def test_paper_pnl_calculation(self):
        # Buy 10 @ 2500
        signal_buy = Signal(
            strategy_name="TEST_STRAT",
            symbol="TCS",
            instrument_token=2953217,
            transaction_type=TransactionType.BUY,
            order_type=OrderType.MARKET,
            quantity=10,
            price=3500.0,
        )
        self.broker.update_quote("TCS", 3500.0)
        self.broker.place_order(signal_buy)

        # Price rises to 3600
        self.broker.update_quote("TCS", 3600.0)
        pos = [p for p in self.broker.get_positions() if p.symbol == "TCS"][0]
        self.assertTrue(pos.unrealized_pnl > 0)


class TestEventBus(unittest.TestCase):
    def test_pub_sub(self):
        test_bus = EventBus()
        received = []

        def handler(data):
            received.append(data)

        test_bus.subscribe(EventType.TICK, handler)
        test_bus.publish(EventType.TICK, {"ltp": 2500.0})
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]["ltp"], 2500.0)


if __name__ == "__main__":
    unittest.main()
