"""
High-Performance Technical Indicators for Indian Market Strategies.
Pure NumPy and Pandas vectorized calculations without heavy external TA libraries.
"""

from __future__ import annotations
from typing import List, Tuple
import numpy as np
import pandas as pd
from core.models import Candle


def candles_to_dataframe(candles: List[Candle]) -> pd.DataFrame:
    """Convert a list of Candle dataclasses to a Pandas DataFrame."""
    data = [
        {
            "timestamp": c.timestamp,
            "open": c.open,
            "high": c.high,
            "low": c.low,
            "close": c.close,
            "volume": c.volume,
        }
        for c in candles
    ]
    df = pd.DataFrame(data)
    if not df.empty:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df.set_index("timestamp", inplace=True)
    return df


def calculate_ema(series: pd.Series, period: int = 20) -> pd.Series:
    """Calculate Exponential Moving Average."""
    return series.ewm(span=period, adjust=False).mean()


def calculate_sma(series: pd.Series, period: int = 20) -> pd.Series:
    """Calculate Simple Moving Average."""
    return series.rolling(window=period).mean()


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calculate Average True Range (ATR)."""
    high = df["high"]
    low = df["low"]
    prev_close = df["close"].shift(1)

    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / period, adjust=False).mean()
    return atr


def calculate_supertrend(
    df: pd.DataFrame, period: int = 10, multiplier: float = 3.0
) -> Tuple[pd.Series, pd.Series]:
    """
    Calculate Supertrend indicator.
    Returns:
        (supertrend_line, direction) where direction is 1 for Bullish (Green), -1 for Bearish (Red).
    """
    hl2 = (df["high"] + df["low"]) / 2.0
    atr = calculate_atr(df, period)

    upper_band = hl2 + (multiplier * atr)
    lower_band = hl2 - (multiplier * atr)

    supertrend = pd.Series(index=df.index, dtype=float)
    direction = pd.Series(index=df.index, dtype=int)

    # Initialize
    in_uptrend = True

    for i in range(len(df)):
        if i == 0:
            supertrend.iloc[i] = lower_band.iloc[i]
            direction.iloc[i] = 1
            continue

        curr_close = df["close"].iloc[i]
        curr_upper = upper_band.iloc[i]
        curr_lower = lower_band.iloc[i]
        prev_upper = upper_band.iloc[i - 1]
        prev_lower = lower_band.iloc[i - 1]

        # Trailing lower band
        if curr_lower > prev_lower or df["close"].iloc[i - 1] < prev_lower:
            pass
        else:
            curr_lower = prev_lower
            lower_band.iloc[i] = curr_lower

        # Trailing upper band
        if curr_upper < prev_upper or df["close"].iloc[i - 1] > prev_upper:
            pass
        else:
            curr_upper = prev_upper
            upper_band.iloc[i] = curr_upper

        if in_uptrend:
            if curr_close < curr_lower:
                in_uptrend = False
                supertrend.iloc[i] = curr_upper
                direction.iloc[i] = -1
            else:
                supertrend.iloc[i] = curr_lower
                direction.iloc[i] = 1
        else:
            if curr_close > curr_upper:
                in_uptrend = True
                supertrend.iloc[i] = curr_lower
                direction.iloc[i] = 1
            else:
                supertrend.iloc[i] = curr_upper
                direction.iloc[i] = -1

    return supertrend, direction


def calculate_vwap(df: pd.DataFrame) -> pd.Series:
    """Calculate Volume Weighted Average Price (VWAP) intraday."""
    typical_price = (df["high"] + df["low"] + df["close"]) / 3.0
    cum_vol_price = (typical_price * df["volume"]).cumsum()
    cum_vol = df["volume"].cumsum()
    return cum_vol_price / cum_vol.replace(0, np.nan)


def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Calculate Relative Strength Index (RSI)."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calculate_cpr(high: float, low: float, close: float) -> dict[str, float]:
    """Calculate Central Pivot Range (CPR) for intraday trading."""
    pivot = (high + low + close) / 3.0
    bc = (high + low) / 2.0
    tc = (pivot - bc) + pivot
    r1 = (2 * pivot) - low
    s1 = (2 * pivot) - high
    return {"pivot": round(pivot, 2), "tc": round(max(tc, bc), 2), "bc": round(min(tc, bc), 2), "r1": round(r1, 2), "s1": round(s1, 2)}
