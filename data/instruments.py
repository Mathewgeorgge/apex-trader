"""
Instrument Master and Token Resolution Manager.
Downloads, caches, and indexes Zerodha instruments (NSE, NFO, BSE) for fast lookup.
"""

from __future__ import annotations
import csv
import io
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import pandas as pd
import requests

from config.settings import settings
from core.models import Instrument

logger = logging.getLogger("InstrumentManager")

INSTRUMENTS_URL = "https://api.kite.trade/instruments"


class InstrumentManager:
    def __init__(self, cache_file: Optional[Path] = None):
        self.cache_file = cache_file or settings.INSTRUMENTS_CACHE_FILE
        self._token_map: Dict[int, Instrument] = {}
        self._symbol_map: Dict[str, Instrument] = {}
        self._loaded: bool = False

    def is_cache_valid(self) -> bool:
        if not self.cache_file.exists():
            return False
        # Instruments expire daily at market open
        mod_time = datetime.fromtimestamp(self.cache_file.stat().st_mtime)
        return mod_time.date() == datetime.now().date()

    def download_instruments(self) -> None:
        """Download latest instruments master CSV directly from Zerodha."""
        logger.info("Downloading latest instruments master from Zerodha Kite...")
        resp = requests.get(INSTRUMENTS_URL, timeout=30)
        resp.raise_exception()
        with open(self.cache_file, "wb") as f:
            f.write(resp.content)
        logger.info(f"Instruments cached successfully to {self.cache_file}")

    def load(self, force_refresh: bool = False) -> None:
        """Load instruments from cache or download if expired."""
        if not self.is_cache_valid() or force_refresh:
            try:
                self.download_instruments()
            except Exception as e:
                logger.warning(f"Failed to download instruments from Kite: {e}")
                if not self.cache_file.exists():
                    self._create_fallback_instruments()

        if self.cache_file.exists():
            logger.info("Loading instruments into memory...")
            df = pd.read_csv(self.cache_file)
            for _, row in df.iterrows():
                try:
                    inst = Instrument(
                        instrument_token=int(row["instrument_token"]),
                        tradingsymbol=str(row["tradingsymbol"]),
                        exchange=str(row.get("exchange", "NSE")),
                        name=str(row.get("name", "")),
                        lot_size=int(row.get("lot_size", 1)),
                        tick_size=float(row.get("tick_size", 0.05)),
                        instrument_type=str(row.get("instrument_type", "EQ")),
                    )
                    self._token_map[inst.instrument_token] = inst
                    self._symbol_map[f"{inst.exchange}:{inst.tradingsymbol}"] = inst
                    if inst.exchange == "NSE":
                        self._symbol_map[inst.tradingsymbol] = inst
                except Exception:
                    continue
            self._loaded = True
            logger.info(f"Loaded {len(self._token_map)} instruments successfully.")

    def _create_fallback_instruments(self) -> None:
        """Fallback list of major Indian indices and blue-chips when offline."""
        defaults = [
            {"instrument_token": 256265, "exchange": "NSE", "tradingsymbol": "NIFTY 50", "name": "Nifty 50", "lot_size": 25, "tick_size": 0.05, "instrument_type": "EQ"},
            {"instrument_token": 260105, "exchange": "NSE", "tradingsymbol": "NIFTY BANK", "name": "Bank Nifty", "lot_size": 15, "tick_size": 0.05, "instrument_type": "EQ"},
            {"instrument_token": 738561, "exchange": "NSE", "tradingsymbol": "RELIANCE", "name": "Reliance Industries", "lot_size": 1, "tick_size": 0.05, "instrument_type": "EQ"},
            {"instrument_token": 341249, "exchange": "NSE", "tradingsymbol": "HDFCBANK", "name": "HDFC Bank", "lot_size": 1, "tick_size": 0.05, "instrument_type": "EQ"},
            {"instrument_token": 408065, "exchange": "NSE", "tradingsymbol": "INFY", "name": "Infosys", "lot_size": 1, "tick_size": 0.05, "instrument_type": "EQ"},
            {"instrument_token": 779521, "exchange": "NSE", "tradingsymbol": "SBIN", "name": "State Bank of India", "lot_size": 1, "tick_size": 0.05, "instrument_type": "EQ"},
            {"instrument_token": 895745, "exchange": "NSE", "tradingsymbol": "TATASTEEL", "name": "Tata Steel", "lot_size": 1, "tick_size": 0.05, "instrument_type": "EQ"},
            {"instrument_token": 2953217, "exchange": "NSE", "tradingsymbol": "TCS", "name": "Tata Consultancy Services", "lot_size": 1, "tick_size": 0.05, "instrument_type": "EQ"},
        ]
        df = pd.DataFrame(defaults)
        df.to_csv(self.cache_file, index=False)
        logger.info("Initialized default fallback instruments file.")

    def get_by_symbol(self, symbol: str, exchange: str = "NSE") -> Optional[Instrument]:
        if not self._loaded:
            self.load()
        return self._symbol_map.get(f"{exchange}:{symbol}") or self._symbol_map.get(symbol)

    def get_by_token(self, token: int) -> Optional[Instrument]:
        if not self._loaded:
            self.load()
        return self._token_map.get(token)

    def search(self, query: str, limit: int = 10) -> List[Instrument]:
        if not self._loaded:
            self.load()
        q = query.upper()
        results = []
        for s, inst in self._symbol_map.items():
            if q in s:
                results.append(inst)
                if len(results) >= limit:
                    break
        return results


instrument_manager = InstrumentManager()
