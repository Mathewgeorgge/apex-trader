"""
Real-Time Market Data Feed & Candle Aggregator.
Supports Zerodha KiteTicker WebSocket streaming and multi-timeframe candle generation.
"""

from __future__ import annotations
import core.compat  # noqa: F401
import logging

from collections import defaultdict
from datetime import datetime
from typing import Callable, Dict, List, Optional
from kiteconnect import KiteTicker

from config.settings import settings
from core.events import EventType, bus
from core.models import Candle, Tick

logger = logging.getLogger("MarketDataFeed")


class CandleAggregator:
    """Aggregates streaming ticks into OHLCV candles of specified timeframe (e.g. 5 minutes)."""

    def __init__(self, interval_minutes: int = 5, on_candle_close: Optional[Callable[[Candle], None]] = None):
        self.interval_minutes = interval_minutes
        self.on_candle_close = on_candle_close
        self.current_candle: Optional[Candle] = None
        self.current_bucket: Optional[int] = None

    def process_tick(self, tick: Tick) -> Optional[Candle]:
        tick_time = tick.timestamp
        # Calculate bucket index for the day (e.g. minutes from midnight // interval)
        total_minutes = tick_time.hour * 60 + tick_time.minute
        bucket = total_minutes // self.interval_minutes

        closed_candle = None
        if self.current_bucket is not None and bucket != self.current_bucket:
            # Bucket changed -> current candle closed
            closed_candle = self.current_candle
            if self.on_candle_close and closed_candle:
                self.on_candle_close(closed_candle)

            # Start new candle
            candle_start = tick_time.replace(
                minute=(bucket * self.interval_minutes) % 60,
                second=0,
                microsecond=0,
            )
            self.current_candle = Candle(
                timestamp=candle_start,
                open=tick.last_price,
                high=tick.last_price,
                low=tick.last_price,
                close=tick.last_price,
                volume=tick.volume,
            )
            self.current_bucket = bucket
        elif self.current_candle is None:
            # First tick
            candle_start = tick_time.replace(
                minute=(bucket * self.interval_minutes) % 60,
                second=0,
                microsecond=0,
            )
            self.current_candle = Candle(
                timestamp=candle_start,
                open=tick.last_price,
                high=tick.last_price,
                low=tick.last_price,
                close=tick.last_price,
                volume=tick.volume,
            )
            self.current_bucket = bucket
        else:
            # Update existing candle
            self.current_candle.high = max(self.current_candle.high, tick.last_price)
            self.current_candle.low = min(self.current_candle.low, tick.last_price)
            self.current_candle.close = tick.last_price
            self.current_candle.volume += tick.volume

        return closed_candle


class MarketDataFeed:
    """Manages WebSocket connections, tick subscriptions, and candle dispatching."""

    def __init__(self, api_key: Optional[str] = None, access_token: Optional[str] = None):
        self.api_key = api_key or settings.KITE_API_KEY
        self.access_token = access_token or settings.KITE_ACCESS_TOKEN
        self.kws: Optional[KiteTicker] = None
        self.subscribed_tokens: List[int] = []
        self.aggregators: Dict[int, Dict[int, CandleAggregator]] = defaultdict(dict)

    def register_aggregator(self, token: int, interval_minutes: int) -> None:
        """Register a candle builder for an instrument at specified minute timeframe."""
        def _publish_candle(candle: Candle):
            bus.publish(EventType.CANDLE, {"token": token, "candle": candle, "interval": interval_minutes})

        self.aggregators[token][interval_minutes] = CandleAggregator(
            interval_minutes=interval_minutes,
            on_candle_close=_publish_candle,
        )

    def initialize_websocket(self) -> None:
        """Initialize Zerodha KiteTicker WebSocket."""
        if not self.api_key or not self.access_token:
            logger.warning("Kite WebSocket requires API key and access token. Skipping WS initialization.")
            return

        self.kws = KiteTicker(self.api_key, self.access_token)
        self.kws.on_ticks = self._on_ticks
        self.kws.on_connect = self._on_connect
        self.kws.on_close = self._on_close
        self.kws.on_error = self._on_error

    def connect(self) -> None:
        if self.kws:
            logger.info("Connecting to Zerodha WebSocket feed...")
            self.kws.connect(threaded=True)

    def subscribe(self, tokens: List[int], mode: str = "full") -> None:
        self.subscribed_tokens.extend(tokens)
        self.subscribed_tokens = list(set(self.subscribed_tokens))
        if self.kws and self.kws.is_connected():
            self.kws.subscribe(tokens)
            if mode == "full":
                self.kws.set_mode(self.kws.MODE_FULL, tokens)
            else:
                self.kws.set_mode(self.kws.MODE_LTP, tokens)

    def _on_connect(self, ws, response):
        logger.info("Connected to Zerodha WebSocket feed successfully.")
        if self.subscribed_tokens:
            ws.subscribe(self.subscribed_tokens)
            ws.set_mode(ws.MODE_FULL, self.subscribed_tokens)

    def _on_ticks(self, ws, ticks):
        for raw in ticks:
            token = raw["instrument_token"]
            tick = Tick(
                instrument_token=token,
                last_price=float(raw.get("last_price", 0.0)),
                volume=int(raw.get("volume", 0)),
                change=float(raw.get("change", 0.0)),
                timestamp=raw.get("timestamp", datetime.now()),
                open=float(raw.get("ohlc", {}).get("open", 0.0)),
                high=float(raw.get("ohlc", {}).get("high", 0.0)),
                low=float(raw.get("ohlc", {}).get("low", 0.0)),
                close=float(raw.get("ohlc", {}).get("close", 0.0)),
                oi=raw.get("oi"),
                depth=raw.get("depth"),
            )
            # Dispatch tick event
            bus.publish(EventType.TICK, tick)

            # Update candle aggregators
            if token in self.aggregators:
                for interval, agg in self.aggregators[token].items():
                    agg.process_tick(tick)

    def _on_close(self, ws, code, reason):
        logger.warning(f"Zerodha WebSocket connection closed: {code} - {reason}")

    def _on_error(self, ws, code, reason):
        logger.error(f"Zerodha WebSocket error: {code} - {reason}")

    def stop(self) -> None:
        if self.kws and self.kws.is_connected():
            self.kws.close()
