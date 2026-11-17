"""
Indian Market Hours and Trading Calendar Utility.
Supports NSE / BSE equity and F&O trading sessions in Asia/Kolkata timezone.
"""

from __future__ import annotations
from datetime import datetime, time
import pytz

IST = pytz.timezone("Asia/Kolkata")

# Market Session Timings (IST)
PRE_MARKET_OPEN = time(9, 0, 0)
PRE_MARKET_CLOSE = time(9, 8, 0)
REGULAR_MARKET_OPEN = time(9, 15, 0)
AUTO_SQUARE_OFF = time(15, 15, 0)
REGULAR_MARKET_CLOSE = time(15, 30, 0)


class MarketHours:
    @staticmethod
    def now_ist() -> datetime:
        """Returns current datetime in IST."""
        return datetime.now(IST)

    @classmethod
    def is_trading_day(cls, dt: datetime | None = None) -> bool:
        """Check if today is Monday to Friday."""
        current = dt or cls.now_ist()
        # 0 = Monday, 4 = Friday, 5 = Saturday, 6 = Sunday
        return current.weekday() < 5

    @classmethod
    def is_market_open(cls, dt: datetime | None = None) -> bool:
        """Check if standard market is currently open (09:15 to 15:30 IST on weekdays)."""
        current = dt or cls.now_ist()
        if not cls.is_trading_day(current):
            return False
        curr_time = current.time()
        return REGULAR_MARKET_OPEN <= curr_time <= REGULAR_MARKET_CLOSE

    @classmethod
    def is_past_square_off(cls, dt: datetime | None = None) -> bool:
        """Check if time is past intraday auto-square-off threshold (15:15 IST)."""
        current = dt or cls.now_ist()
        return current.time() >= AUTO_SQUARE_OFF

    @classmethod
    def can_open_new_position(cls, dt: datetime | None = None) -> bool:
        """New positions should only be opened during safe trading window (9:18 AM to 15:05 PM)."""
        current = dt or cls.now_ist()
        if not cls.is_market_open(current):
            return False
        curr_time = current.time()
        # Avoid opening new positions in the very first 3 minutes or last 25 minutes
        return time(9, 18, 0) <= curr_time <= time(15, 5, 0)
