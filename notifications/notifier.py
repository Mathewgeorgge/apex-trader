"""
Multi-Channel Alert and Notification System (Telegram & Formatted Logs).
"""

from __future__ import annotations
import logging
from typing import Any, Dict
import requests

from config.settings import settings
from core.events import EventType, bus

logger = logging.getLogger("Notifier")


class Notifier:
    def __init__(self):
        self.telegram_enabled = settings.TELEGRAM_ENABLED
        self.bot_token = settings.TELEGRAM_BOT_TOKEN
        self.chat_id = settings.TELEGRAM_CHAT_ID

        # Register event bus listeners
        bus.subscribe(EventType.ORDER_FILLED, self._on_order_filled)
        bus.subscribe(EventType.RISK_BREACH, self._on_risk_breach)

    def send_telegram(self, message: str) -> bool:
        """Send immediate Telegram markdown message."""
        if not (self.telegram_enabled and self.bot_token and self.chat_id):
            return False
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            payload = {"chat_id": self.chat_id, "text": message, "parse_mode": "Markdown"}
            resp = requests.post(url, json=payload, timeout=5)
            return resp.status_code == 200
        except Exception as e:
            logger.warning(f"Failed to deliver Telegram notification: {e}")
            return False

    def notify_order(self, order_id: str, symbol: str, tx_type: str, qty: int, price: float, tag: str = "") -> None:
        msg = (
            f"🚀 *ORDER EXECUTED*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"• *Symbol:* `{symbol}`\n"
            f"• *Action:* `{tx_type}`\n"
            f"• *Quantity:* `{qty}`\n"
            f"• *Price:* `Rs. {price:.2f}`\n"
            f"• *Order ID:* `{order_id}`\n"
            f"• *Tag:* `{tag}`"
        )
        print(f"\n[ALERT] {tx_type} {qty} {symbol} @ Rs. {price:.2f} ({order_id})")
        self.send_telegram(msg)

    def notify_risk_alert(self, reason: str) -> None:
        msg = (
            f"⚠️ *CIRCUIT BREAKER ALERT*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"• *Reason:* {reason}\n"
            f"• *Action:* All trading halted & positions squared off."
        )
        print(f"\n[CRITICAL ALERT] {reason}")
        self.send_telegram(msg)

    def _on_order_filled(self, data: Any) -> None:
        if isinstance(data, dict):
            self.notify_order(
                data.get("order_id", ""),
                data.get("symbol", ""),
                data.get("type", ""),
                data.get("qty", 0),
                data.get("price", 0.0),
                data.get("tag", ""),
            )

    def _on_risk_breach(self, data: Any) -> None:
        reason = data.get("reason", "Risk limit exceeded") if isinstance(data, dict) else str(data)
        self.notify_risk_alert(reason)


notifier = Notifier()
