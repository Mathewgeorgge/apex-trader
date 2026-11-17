"""
Zerodha & SEBI Indian Financial Markets Statutory Charges & Brokerage Calculator.
Accurately computes:
- Brokerage (Zerodha flat ₹20 or 0.03%)
- STT / CTT (Securities Transaction Tax)
- NSE / BSE Exchange Transaction Charges
- GST (18% on Brokerage + Exchange charges + SEBI charges)
- SEBI Turnover Fees (₹10 / crore)
- Stamp Duty (State)
- Breakeven points per share/lot
"""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum


class Segment(str, Enum):
    EQUITY_INTRADAY = "EQUITY_INTRADAY"   # MIS
    EQUITY_DELIVERY = "EQUITY_DELIVERY"   # CNC
    EQUITY_FUTURES = "EQUITY_FUTURES"     # NFO Futures
    EQUITY_OPTIONS = "EQUITY_OPTIONS"     # NFO Options


@dataclass
class TradeCharges:
    turnover_buy: float
    turnover_sell: float
    total_turnover: float
    brokerage: float
    stt: float
    exchange_charges: float
    sebi_charges: float
    stamp_duty: float
    gst: float
    total_charges: float
    breakeven_points: float
    gross_pnl: float
    net_pnl: float


class ZerodhaChargeCalculator:
    """
    SEBI & Zerodha fee calculation engine.
    Aligned with Zerodha brokerage calculator rules.
    """

    @staticmethod
    def calculate(
        buy_price: float,
        sell_price: float,
        quantity: int,
        segment: Segment = Segment.EQUITY_INTRADAY,
    ) -> TradeCharges:
        buy_val = buy_price * quantity
        sell_val = sell_price * quantity
        turnover = buy_val + sell_val
        gross_pnl = (sell_price - buy_price) * quantity

        brokerage = 0.0
        stt = 0.0
        exchange_charges = 0.0
        stamp_duty = 0.0

        if segment == Segment.EQUITY_INTRADAY:
            # Brokerage: 0.03% or Rs. 20 per executed order, whichever is lower
            buy_brokerage = min(20.0, buy_val * 0.0003)
            sell_brokerage = min(20.0, sell_val * 0.0003)
            brokerage = buy_brokerage + sell_brokerage

            # STT: 0.025% on sell side only for intraday
            stt = round(sell_val * 0.00025, 2)

            # Exchange txn charge (NSE): 0.00297% on turnover
            exchange_charges = round(turnover * 0.0000297, 2)

            # Stamp duty: 0.003% on buy side
            stamp_duty = round(buy_val * 0.00003, 2)

        elif segment == Segment.EQUITY_OPTIONS:
            # Options: Flat Rs. 20 per executed order
            brokerage = 40.0  # Buy order (Rs 20) + Sell order (Rs 20)

            # STT: 0.1% on sell side premium turnover
            stt = round(sell_val * 0.001, 2)

            # Exchange txn charge (NSE Options): 0.03503% on premium turnover
            exchange_charges = round(turnover * 0.0003503, 2)

            # Stamp duty: 0.003% on buy side premium
            stamp_duty = round(buy_val * 0.00003, 2)

        elif segment == Segment.EQUITY_FUTURES:
            # Futures: 0.03% or Rs. 20 whichever is lower
            brokerage = min(20.0, buy_val * 0.0003) + min(20.0, sell_val * 0.0003)
            # STT: 0.02% on sell side
            stt = round(sell_val * 0.0002, 2)
            # Exchange charge: 0.00173%
            exchange_charges = round(turnover * 0.0000173, 2)
            # Stamp duty: 0.002% on buy side
            stamp_duty = round(buy_val * 0.00002, 2)

        else:  # EQUITY_DELIVERY
            brokerage = 0.0
            stt = round(turnover * 0.001, 2)  # 0.1% on both buy & sell
            exchange_charges = round(turnover * 0.0000297, 2)
            stamp_duty = round(buy_val * 0.00015, 2)  # 0.015% on buy

        # SEBI Turnover Charges: Rs 10 per crore (0.0001%)
        sebi_charges = round(turnover * 0.000001, 2)

        # GST: 18% on (Brokerage + Exchange charges + SEBI charges)
        gst_base = brokerage + exchange_charges + sebi_charges
        gst = round(gst_base * 0.18, 2)

        total_charges = round(brokerage + stt + exchange_charges + sebi_charges + stamp_duty + gst, 2)
        breakeven_points = round(total_charges / quantity, 2) if quantity > 0 else 0.0
        net_pnl = round(gross_pnl - total_charges, 2)

        return TradeCharges(
            turnover_buy=round(buy_val, 2),
            turnover_sell=round(sell_val, 2),
            total_turnover=round(turnover, 2),
            brokerage=round(brokerage, 2),
            stt=stt,
            exchange_charges=exchange_charges,
            sebi_charges=sebi_charges,
            stamp_duty=stamp_duty,
            gst=gst,
            total_charges=total_charges,
            breakeven_points=breakeven_points,
            gross_pnl=round(gross_pnl, 2),
            net_pnl=net_pnl,
        )
