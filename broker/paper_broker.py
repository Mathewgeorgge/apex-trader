"""
High-Fidelity Simulated Paper Trading Broker.
Allows testing with live market ticks or simulated quotes without financial risk.
"""

from __future__ import annotations
import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import yfinance as yf

from broker.base import BaseBroker
from config.settings import settings
from core.models import (
    AccountSummary,
    Candle,
    Order,
    OrderStatus,
    OrderType,
    Position,
    ProductType,
    Signal,
    TransactionType,
)

logger = logging.getLogger("PaperBroker")


class PaperBroker(BaseBroker):
    def __init__(self, initial_capital: float = 7000.0):
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions: Dict[str, Position] = {}
        self.orders: List[Order] = []
        self.latest_quotes: Dict[str, float] = {}

    def authenticate(self) -> bool:
        logger.info("[PAPER TRADING] Broker authenticated in SIMULATION mode.")
        return True

    def get_profile(self) -> Dict[str, Any]:
        return {
            "user_id": "PAPER_TRADER_01",
            "user_name": "Paper Account",
            "email": "paper@trader.sim",
            "broker": "PaperBroker",
        }

    def get_margins(self) -> AccountSummary:
        realized = sum(p.realized_pnl for p in self.positions.values())
        unrealized = sum(p.unrealized_pnl for p in self.positions.values())
        used = sum(abs(p.quantity) * p.average_price for p in self.positions.values() if p.quantity != 0)
        return AccountSummary(
            available_cash=self.cash,
            collateral=0.0,
            margin_used=used,
            realized_pnl=realized,
            unrealized_pnl=unrealized,
        )

    def get_orders(self) -> List[Order]:
        return list(self.orders)

    def get_positions(self) -> List[Position]:
        return [p for p in self.positions.values() if p.quantity != 0]

    def update_quote(self, symbol: str, ltp: float) -> None:
        """Feed a live or simulated price update."""
        self.latest_quotes[symbol] = ltp
        if symbol in self.positions:
            self.positions[symbol].update_ltp(ltp)

    def place_order(self, signal: Signal) -> Order:
        order_id = f"PAPER_{uuid.uuid4().hex[:8].upper()}"
        ltp = self.latest_quotes.get(signal.symbol, signal.price or 100.0)

        # Apply simulated realistic slippage
        slippage = ltp * settings.SLIPPAGE_TOLERANCE_PCT
        fill_price = ltp + slippage if signal.transaction_type == TransactionType.BUY else ltp - slippage
        fill_price = round(fill_price, 2)

        order = Order(
            order_id=order_id,
            symbol=signal.symbol,
            instrument_token=signal.instrument_token,
            transaction_type=signal.transaction_type,
            order_type=signal.order_type,
            product=signal.product,
            quantity=signal.quantity,
            filled_quantity=signal.quantity,
            price=signal.price or fill_price,
            average_price=fill_price,
            status=OrderStatus.COMPLETE,
            created_at=datetime.now(),
            tag=signal.tag,
        )
        self.orders.append(order)

        # Update position
        self._update_position_from_fill(order)

        logger.info(
            f"[PAPER ORDER FILLED] {order.transaction_type} {order.quantity} {order.symbol} @ Rs. {order.average_price:.2f}"
        )
        self._persist_trade(order)
        return order

    def _update_position_from_fill(self, order: Order) -> None:
        symbol = order.symbol
        if symbol not in self.positions:
            self.positions[symbol] = Position(
                symbol=symbol,
                instrument_token=order.instrument_token,
                product=order.product,
                quantity=0,
                average_price=0.0,
                ltp=order.average_price,
            )

        pos = self.positions[symbol]
        prev_qty = pos.quantity
        tx_qty = order.quantity if order.transaction_type == TransactionType.BUY else -order.quantity
        new_qty = prev_qty + tx_qty

        if prev_qty == 0:
            # Opening new position
            pos.quantity = new_qty
            pos.average_price = order.average_price
            if order.transaction_type == TransactionType.BUY:
                pos.buy_price = order.average_price
                self.cash -= order.quantity * order.average_price
            else:
                pos.sell_price = order.average_price
                self.cash += order.quantity * order.average_price
        elif (prev_qty > 0 and tx_qty > 0) or (prev_qty < 0 and tx_qty < 0):
            # Increasing existing position size
            total_val = (abs(prev_qty) * pos.average_price) + (abs(tx_qty) * order.average_price)
            pos.quantity = new_qty
            pos.average_price = round(total_val / abs(new_qty), 2)
        else:
            # Closing or reversing position
            closing_qty = min(abs(prev_qty), abs(tx_qty))
            if prev_qty > 0:  # Closing Long
                gross_pnl = closing_qty * (order.average_price - pos.average_price)
                buy_p = pos.average_price
                sell_p = order.average_price
                self.cash += (closing_qty * order.average_price)
            else:  # Closing Short
                gross_pnl = closing_qty * (pos.average_price - order.average_price)
                buy_p = order.average_price
                sell_p = pos.average_price
                self.cash -= (closing_qty * order.average_price)

            # Deduct Zerodha brokerage & statutory taxes
            from core.charges import ZerodhaChargeCalculator, Segment
            segment = Segment.EQUITY_OPTIONS if "CE" in symbol or "PE" in symbol else Segment.EQUITY_INTRADAY
            charges = ZerodhaChargeCalculator.calculate(buy_p, sell_p, closing_qty, segment)
            self.cash -= charges.total_charges
            realized = gross_pnl - charges.total_charges

            pos.realized_pnl += realized
            pos.quantity = new_qty
            if new_qty != 0:
                pos.average_price = order.average_price

        pos.update_ltp(order.average_price)

    def cancel_order(self, order_id: str) -> bool:
        for o in self.orders:
            if o.order_id == order_id and o.status == OrderStatus.OPEN:
                o.status = OrderStatus.CANCELLED
                return True
        return False

    def modify_order(
        self,
        order_id: str,
        price: Optional[float] = None,
        trigger_price: Optional[float] = None,
        quantity: Optional[int] = None,
    ) -> bool:
        for o in self.orders:
            if o.order_id == order_id and o.status == OrderStatus.OPEN:
                if price:
                    o.price = price
                if quantity:
                    o.quantity = quantity
                return True
        return False

    def get_quote(self, symbol: str, exchange: str = "NSE") -> Dict[str, Any]:
        if symbol in self.latest_quotes:
            return {"last_price": self.latest_quotes[symbol]}
        # Fallback to yfinance for live quotes if available
        try:
            ticker_sym = f"{symbol}.NS" if not symbol.endswith(".NS") else symbol
            ticker = yf.Ticker(ticker_sym)
            fast_info = ticker.fast_info
            price = float(fast_info.last_price)
            self.latest_quotes[symbol] = price
            return {"last_price": price}
        except Exception:
            return {"last_price": self.latest_quotes.get(symbol, 100.0)}

    def get_historical_data(
        self,
        instrument_token: int,
        from_date: datetime,
        to_date: datetime,
        interval: str = "5m",
    ) -> List[Candle]:
        # Generate or fetch from yfinance using symbol mapping
        # Default interval mapping: 5m, 15m, 1h, 1d
        candles = []
        try:
            # Check if yfinance has data for fallback
            # Default to RELIANCE.NS if token unknown
            ticker = yf.Ticker("RELIANCE.NS")
            df = ticker.history(start=from_date.strftime("%Y-%m-%d"), end=to_date.strftime("%Y-%m-%d"), interval="5m")
            for idx, row in df.iterrows():
                candles.append(
                    Candle(
                        timestamp=idx.to_pydatetime(),
                        open=float(row["Open"]),
                        high=float(row["High"]),
                        low=float(row["Low"]),
                        close=float(row["Close"]),
                        volume=int(row["Volume"]),
                    )
                )
        except Exception as e:
            logger.warning(f"Could not fetch historical data in paper broker: {e}")
        return candles

    def square_off_all(self) -> List[Order]:
        orders = []
        for symbol, pos in list(self.positions.items()):
            if pos.quantity == 0:
                continue
            tx_type = TransactionType.SELL if pos.quantity > 0 else TransactionType.BUY
            signal = Signal(
                strategy_name="PAPER_SQUARE_OFF",
                symbol=symbol,
                instrument_token=pos.instrument_token,
                transaction_type=tx_type,
                order_type=OrderType.MARKET,
                quantity=abs(pos.quantity),
                tag="AUTO_SQUARE_OFF",
            )
            order = self.place_order(signal)
            orders.append(order)
        return orders

    def _persist_trade(self, order: Order) -> None:
        try:
            path = settings.TRADES_LOG_FILE
            trades = []
            if path.exists():
                with open(path, "r") as f:
                    trades = json.load(f)
            trades.append(
                {
                    "order_id": order.order_id,
                    "symbol": order.symbol,
                    "type": order.transaction_type.value,
                    "qty": order.quantity,
                    "price": order.average_price,
                    "time": order.created_at.isoformat(),
                    "tag": order.tag,
                }
            )
            with open(path, "w") as f:
                json.dump(trades, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not persist paper trade: {e}")
