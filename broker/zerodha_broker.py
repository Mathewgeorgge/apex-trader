"""
Zerodha Kite Connect Broker Implementation.
Full integration with KiteConnect Python SDK with automatic token persistence.
"""

from __future__ import annotations
import core.compat  # noqa: F401
import json

import logging
from datetime import datetime, time
from typing import Any, Dict, List, Optional
import pyotp
import requests
from kiteconnect import KiteConnect
from kiteconnect.exceptions import (
    GeneralException,
    InputException,
    NetworkException,
    OrderException,
    TokenException,
)

from broker.base import BaseBroker
from config.settings import settings
from core.exceptions import AuthenticationError, OrderExecutionError
from core.models import (
    AccountSummary,
    Candle,
    Order,
    OrderStatus,
    Position,
    ProductType,
    Signal,
    TransactionType,
    OrderType,
)

logger = logging.getLogger("ZerodhaBroker")


class ZerodhaBroker(BaseBroker):
    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None):
        self.api_key = api_key or settings.KITE_API_KEY
        self.api_secret = api_secret or settings.KITE_API_SECRET
        self.kite = KiteConnect(api_key=self.api_key)
        self.access_token: Optional[str] = None
        self._authenticated: bool = False

    def get_login_url(self) -> str:
        """Returns the Zerodha web login URL to authorize the API app."""
        return self.kite.login_url()

    def generate_session_from_token(self, request_token: str) -> str:
        """Exchange manual request_token from login redirect URL for access_token."""
        try:
            data = self.kite.generate_session(request_token, api_secret=self.api_secret)
            self.access_token = data["access_token"]
            self.kite.set_access_token(self.access_token)
            self._save_token_cache(self.access_token)
            self._authenticated = True
            logger.info("Successfully generated and cached Zerodha access_token.")
            return self.access_token
        except Exception as e:
            raise AuthenticationError(f"Failed to generate Zerodha session: {e}")

    def auto_login_with_totp(self) -> str:
        """
        Automated headless login using user ID, password, and TOTP secret.
        Requires KITE_USER_ID, KITE_PASSWORD, and KITE_TOTP_SECRET in .env.
        """
        if not (settings.KITE_USER_ID and settings.KITE_PASSWORD and settings.KITE_TOTP_SECRET):
            raise AuthenticationError(
                "Automated TOTP login requires KITE_USER_ID, KITE_PASSWORD, and KITE_TOTP_SECRET."
            )

        logger.info("Attempting automated Zerodha TOTP login...")
        session = requests.Session()
        try:
            # Step 1: Login with username and password
            login_url = "https://kite.zerodha.com/api/login"
            resp = session.post(
                login_url,
                data={"user_id": settings.KITE_USER_ID, "password": settings.KITE_PASSWORD},
                timeout=10,
            )
            login_data = resp.json()
            if login_data.get("status") != "success":
                raise AuthenticationError(f"Zerodha login failed: {login_data.get('message')}")

            request_id = login_data["data"]["request_id"]

            # Step 2: Generate current TOTP code
            totp = pyotp.TOTP(settings.KITE_TOTP_SECRET.replace(" ", ""))
            twofa_code = totp.now()

            # Step 3: Submit 2FA TOTP
            twofa_url = "https://kite.zerodha.com/api/twofa"
            twofa_resp = session.post(
                twofa_url,
                data={
                    "user_id": settings.KITE_USER_ID,
                    "request_id": request_id,
                    "twofa_value": twofa_code,
                    "twofa_type": "totp",
                    "skip_session": "true",
                },
                timeout=10,
            )
            twofa_data = twofa_resp.json()
            if twofa_data.get("status") != "success":
                raise AuthenticationError(f"Zerodha 2FA failed: {twofa_data.get('message')}")

            # Step 4: Authorize app via Kite Connect redirect URL to grab request_token
            auth_url = f"https://kite.zerodha.com/connect/login?v=3&api_key={self.api_key}"
            auth_resp = session.get(auth_url, allow_redirects=False, timeout=10)
            redirect_url = auth_resp.headers.get("Location", "")

            if "request_token=" not in redirect_url:
                raise AuthenticationError("Could not capture request_token from redirect.")

            # Extract request_token from redirect url
            import urllib.parse
            parsed = urllib.parse.urlparse(redirect_url)
            params = urllib.parse.parse_qs(parsed.query)
            request_token = params["request_token"][0]

            return self.generate_session_from_token(request_token)
        except Exception as e:
            logger.error(f"Auto TOTP login error: {e}")
            raise AuthenticationError(f"Auto TOTP login error: {e}")

    def authenticate(self) -> bool:
        """Authenticate using cached token, manual env token, or auto TOTP login."""
        # Check explicit env token first
        if settings.KITE_ACCESS_TOKEN:
            self.access_token = settings.KITE_ACCESS_TOKEN
            self.kite.set_access_token(self.access_token)
            if self._validate_session():
                self._authenticated = True
                return True

        # Check cached token file
        cached = self._load_token_cache()
        if cached:
            self.access_token = cached
            self.kite.set_access_token(cached)
            if self._validate_session():
                self._authenticated = True
                logger.info("Zerodha authenticated using valid cached daily token.")
                return True

        # Try automated TOTP login if credentials present
        if settings.KITE_USER_ID and settings.KITE_PASSWORD and settings.KITE_TOTP_SECRET:
            try:
                self.auto_login_with_totp()
                return True
            except Exception as e:
                logger.warning(f"Automated TOTP login could not complete: {e}")

        logger.info(f"Manual authentication needed. Please open URL in browser:\n{self.get_login_url()}")
        return False

    def _validate_session(self) -> bool:
        """Quick call to verify token validity."""
        try:
            self.kite.profile()
            return True
        except TokenException:
            logger.warning("Cached Zerodha access token is expired or invalid.")
            return False
        except Exception as e:
            logger.warning(f"Session validation check failed: {e}")
            return False

    def _load_token_cache(self) -> Optional[str]:
        cache_path = settings.TOKEN_CACHE_FILE
        if not cache_path.exists():
            return None
        try:
            with open(cache_path, "r") as f:
                data = json.load(f)
            # Kite tokens reset at 6:00 AM IST daily
            saved_date = data.get("date")
            today = datetime.now().strftime("%Y-%m-%d")
            if saved_date == today:
                return data.get("access_token")
        except Exception:
            pass
        return None

    def _save_token_cache(self, token: str) -> None:
        try:
            cache_path = settings.TOKEN_CACHE_FILE
            with open(cache_path, "w") as f:
                json.dump({"access_token": token, "date": datetime.now().strftime("%Y-%m-%d")}, f)
        except Exception as e:
            logger.warning(f"Failed to cache access token to disk: {e}")

    def get_profile(self) -> Dict[str, Any]:
        return self.kite.profile()

    def get_margins(self) -> AccountSummary:
        margins = self.kite.margins(segment="equity")
        available = margins.get("available", {})
        utilised = margins.get("utilised", {})
        return AccountSummary(
            available_cash=float(available.get("cash", 0.0)),
            collateral=float(available.get("collateral", 0.0)),
            margin_used=float(utilised.get("debit", 0.0)),
            realized_pnl=float(utilised.get("realised_m2m", 0.0)),
            unrealized_pnl=float(utilised.get("unrealised_m2m", 0.0)),
        )

    def get_orders(self) -> List[Order]:
        raw_orders = self.kite.orders()
        orders = []
        for o in raw_orders:
            ttype = TransactionType.BUY if o["transaction_type"] == "BUY" else TransactionType.SELL
            status_map = {
                "COMPLETE": OrderStatus.COMPLETE,
                "OPEN": OrderStatus.OPEN,
                "CANCELLED": OrderStatus.CANCELLED,
                "REJECTED": OrderStatus.REJECTED,
                "TRIGGER PENDING": OrderStatus.PENDING,
            }
            order = Order(
                order_id=str(o["order_id"]),
                symbol=o["tradingsymbol"],
                instrument_token=o.get("instrument_token", 0),
                transaction_type=ttype,
                order_type=OrderType(o["order_type"]),
                product=ProductType(o["product"]),
                quantity=int(o["quantity"]),
                filled_quantity=int(o["filled_quantity"]),
                price=float(o.get("price", 0.0)),
                trigger_price=float(o.get("trigger_price", 0.0)),
                average_price=float(o.get("average_price", 0.0)),
                status=status_map.get(o["status"], OrderStatus.PENDING),
                rejection_reason=o.get("status_message"),
                tag=o.get("tag", ""),
            )
            orders.append(order)
        return orders

    def get_positions(self) -> List[Position]:
        raw = self.kite.positions()
        net = raw.get("net", [])
        positions = []
        for p in net:
            pos = Position(
                symbol=p["tradingsymbol"],
                instrument_token=p["instrument_token"],
                product=ProductType(p["product"]),
                quantity=int(p["quantity"]),
                buy_price=float(p.get("buy_price", 0.0)),
                sell_price=float(p.get("sell_price", 0.0)),
                average_price=float(p.get("average_price", 0.0)),
                ltp=float(p.get("last_price", 0.0)),
                realized_pnl=float(p.get("pnl", 0.0)),
                unrealized_pnl=float(p.get("m2m", 0.0)),
            )
            positions.append(pos)
        return positions

    def place_order(self, signal: Signal) -> Order:
        try:
            exchange = "NSE" if not signal.symbol.startswith("NIFTY") or "FUT" not in signal.symbol else "NFO"
            kite_tx_type = self.kite.TRANSACTION_TYPE_BUY if signal.transaction_type == TransactionType.BUY else self.kite.TRANSACTION_TYPE_SELL
            kite_order_type = self.kite.ORDER_TYPE_MARKET if signal.order_type == OrderType.MARKET else self.kite.ORDER_TYPE_LIMIT

            order_id = self.kite.place_order(
                variety=self.kite.VARIETY_REGULAR,
                exchange=exchange,
                tradingsymbol=signal.symbol,
                transaction_type=kite_tx_type,
                quantity=signal.quantity,
                product=self.kite.PRODUCT_MIS if signal.product == ProductType.MIS else self.kite.PRODUCT_CNC,
                order_type=kite_order_type,
                price=signal.price if signal.order_type == OrderType.LIMIT else None,
                tag=signal.tag or signal.strategy_name[:20],
            )
            logger.info(f"Zerodha Order Placed successfully: {order_id} ({signal.symbol} {signal.transaction_type} {signal.quantity})")
            return Order(
                order_id=str(order_id),
                symbol=signal.symbol,
                instrument_token=signal.instrument_token,
                transaction_type=signal.transaction_type,
                order_type=signal.order_type,
                product=signal.product,
                quantity=signal.quantity,
                price=signal.price,
                status=OrderStatus.PENDING,
                tag=signal.tag,
            )
        except OrderException as e:
            logger.error(f"Zerodha Order rejected: {e}")
            raise OrderExecutionError(f"Order rejected by Zerodha: {e}")
        except Exception as e:
            logger.error(f"Unexpected error placing order on Zerodha: {e}")
            raise OrderExecutionError(f"Zerodha order failure: {e}")

    def cancel_order(self, order_id: str) -> bool:
        try:
            self.kite.cancel_order(variety=self.kite.VARIETY_REGULAR, order_id=order_id)
            return True
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return False

    def modify_order(
        self,
        order_id: str,
        price: Optional[float] = None,
        trigger_price: Optional[float] = None,
        quantity: Optional[int] = None,
    ) -> bool:
        try:
            self.kite.modify_order(
                variety=self.kite.VARIETY_REGULAR,
                order_id=order_id,
                price=price,
                trigger_price=trigger_price,
                quantity=quantity,
            )
            return True
        except Exception as e:
            logger.error(f"Failed to modify order {order_id}: {e}")
            return False

    def get_quote(self, symbol: str, exchange: str = "NSE") -> Dict[str, Any]:
        key = f"{exchange}:{symbol}"
        return self.kite.quote(key).get(key, {})

    def get_historical_data(
        self,
        instrument_token: int,
        from_date: datetime,
        to_date: datetime,
        interval: str = "5minute",
    ) -> List[Candle]:
        raw_candles = self.kite.historical_data(
            instrument_token=instrument_token,
            from_date=from_date,
            to_date=to_date,
            interval=interval,
        )
        candles = []
        for c in raw_candles:
            candles.append(
                Candle(
                    timestamp=c["date"],
                    open=c["open"],
                    high=c["high"],
                    low=c["low"],
                    close=c["close"],
                    volume=c["volume"],
                )
            )
        return candles

    def square_off_all(self) -> List[Order]:
        """Emergency circuit breaker exit: squares off all open positions."""
        closed_orders = []
        positions = self.get_positions()
        for pos in positions:
            if pos.quantity == 0:
                continue
            tx_type = TransactionType.SELL if pos.quantity > 0 else TransactionType.BUY
            qty = abs(pos.quantity)
            signal = Signal(
                strategy_name="EMERGENCY_SQUARE_OFF",
                symbol=pos.symbol,
                instrument_token=pos.instrument_token,
                transaction_type=tx_type,
                order_type=OrderType.MARKET,
                quantity=qty,
                product=pos.product,
                tag="KILL_SWITCH",
            )
            try:
                order = self.place_order(signal)
                closed_orders.append(order)
            except Exception as e:
                logger.critical(f"Failed to square off position {pos.symbol}: {e}")
        return closed_orders
