"""
Configuration and Environment Settings for Zerodha Algo Trader.
"""

from __future__ import annotations
import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Base paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
STORAGE_DIR = PROJECT_ROOT / "storage"
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

# Load .env file
load_dotenv(PROJECT_ROOT / ".env")


class Settings:
    # Execution Mode: PAPER or LIVE
    TRADING_MODE: str = os.getenv("TRADING_MODE", "PAPER").upper()

    # Zerodha Credentials
    KITE_API_KEY: str = os.getenv("KITE_API_KEY", "")
    KITE_API_SECRET: str = os.getenv("KITE_API_SECRET", "")
    KITE_USER_ID: str = os.getenv("KITE_USER_ID", "")
    KITE_PASSWORD: str = os.getenv("KITE_PASSWORD", "")
    KITE_TOTP_SECRET: str = os.getenv("KITE_TOTP_SECRET", "")
    KITE_ACCESS_TOKEN: Optional[str] = os.getenv("KITE_ACCESS_TOKEN", None)

    # Risk Management (Calibrated for 7,000 Account)
    MAX_DAILY_LOSS: float = float(os.getenv("MAX_DAILY_LOSS", "200.0"))
    MAX_CAPITAL_PER_TRADE: float = float(os.getenv("MAX_CAPITAL_PER_TRADE", "3500.0"))
    MAX_TRADES_PER_DAY: int = int(os.getenv("MAX_TRADES_PER_DAY", "10"))
    MAX_OPEN_POSITIONS: int = int(os.getenv("MAX_OPEN_POSITIONS", "3"))
    SLIPPAGE_TOLERANCE_PCT: float = float(os.getenv("SLIPPAGE_TOLERANCE_PCT", "0.001"))
    AUTO_SQUARE_OFF_TIME: str = os.getenv("AUTO_SQUARE_OFF_TIME", "15:15:00")

    # Order defaults
    DEFAULT_PRODUCT: str = os.getenv("DEFAULT_PRODUCT", "MIS").upper()  # MIS / CNC / NRML

    # Notifications
    TELEGRAM_ENABLED: bool = os.getenv("TELEGRAM_ENABLED", "false").lower() in ("true", "1", "yes")
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")

    # Storage paths
    DATA_DIR: Path = STORAGE_DIR
    TOKEN_CACHE_FILE: Path = STORAGE_DIR / "access_token.json"
    INSTRUMENTS_CACHE_FILE: Path = STORAGE_DIR / "instruments_cache.csv"
    TRADES_LOG_FILE: Path = STORAGE_DIR / "trades.json"

    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    @classmethod
    def is_paper(cls) -> bool:
        return cls.TRADING_MODE != "LIVE"

    @classmethod
    def validate_keys(cls) -> None:
        if not cls.KITE_API_KEY or not cls.KITE_API_SECRET:
            if cls.TRADING_MODE == "LIVE":
                raise ValueError("KITE_API_KEY and KITE_API_SECRET must be set in .env for LIVE trading!")


settings = Settings()
