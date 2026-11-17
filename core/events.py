"""
Event Bus and Event Definitions for Reactive Trading Architecture.
"""

from __future__ import annotations
from typing import Callable, Dict, List, Any
import logging

logger = logging.getLogger("EventBus")


class EventType:
    TICK = "TICK"
    CANDLE = "CANDLE"
    SIGNAL = "SIGNAL"
    ORDER_SUBMITTED = "ORDER_SUBMITTED"
    ORDER_FILLED = "ORDER_FILLED"
    ORDER_CANCELLED = "ORDER_CANCELLED"
    ORDER_REJECTED = "ORDER_REJECTED"
    POSITION_UPDATED = "POSITION_UPDATED"
    RISK_BREACH = "RISK_BREACH"
    MARKET_CLOSE = "MARKET_CLOSE"


class EventBus:
    """Thread-safe and synchronous publish-subscribe event broker."""

    def __init__(self):
        self._subscribers: Dict[str, List[Callable[[Any], None]]] = {}

    def subscribe(self, event_type: str, handler: Callable[[Any], None]) -> None:
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        if handler not in self._subscribers[event_type]:
            self._subscribers[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: Callable[[Any], None]) -> None:
        if event_type in self._subscribers and handler in self._subscribers[event_type]:
            self._subscribers[event_type].remove(handler)

    def publish(self, event_type: str, data: Any) -> None:
        handlers = self._subscribers.get(event_type, [])
        for handler in handlers:
            try:
                handler(data)
            except Exception as e:
                logger.error(f"Error handling event {event_type} in {handler.__name__}: {e}", exc_info=True)


# Global singleton instance
bus = EventBus()
