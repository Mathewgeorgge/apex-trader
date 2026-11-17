"""
Zerodha Algo Trader - Main CLI Controller.
"""

from __future__ import annotations
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

# Initialize compatibility patch for Windows twisted sockets
import core.compat  # noqa: F401

import argparse
import logging
import time
from datetime import datetime, timedelta


from broker.paper_broker import PaperBroker
from broker.zerodha_broker import ZerodhaBroker
from config.market_hours import MarketHours
from config.settings import settings
from data.feed import MarketDataFeed
from data.instruments import instrument_manager
from engine.backtester import Backtester
from engine.execution_engine import ExecutionEngine
from risk.risk_manager import RiskManager
from strategies.orb_strategy import ORBStrategy
from strategies.straddle_strategy import ShortStraddleStrategy
from strategies.supertrend_ema import SupertrendEMAStrategy

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("Main")


def get_broker(mode: str):
    if mode.upper() == "LIVE":
        settings.validate_keys()
        return ZerodhaBroker()
    return PaperBroker()


def cmd_login(args):
    """Handle Zerodha authentication and access token generation."""
    broker = ZerodhaBroker()
    print("=" * 60)
    print("ZERODHA KITE CONNECT AUTHENTICATION")
    print("=" * 60)

    if settings.KITE_USER_ID and settings.KITE_PASSWORD and settings.KITE_TOTP_SECRET:
        print("Found automated login credentials in .env. Attempting automated TOTP login...")
        try:
            token = broker.auto_login_with_totp()
            print(f"SUCCESS: Generated session access token: {token[:6]}...{token[-4:]}")
            print(f"Token cached to {settings.TOKEN_CACHE_FILE}")
            return
        except Exception as e:
            print(f"Auto-login failed: {e}\nFalling back to manual authorization URL...")

    login_url = broker.get_login_url()
    print("\nPlease follow these steps to authenticate manually:")
    print(f"1. Open this URL in your browser:\n   {login_url}\n")
    print("2. Log in with your Zerodha credentials and 2FA.")
    print("3. After login, your browser will redirect to your registered redirect URL.")
    print("4. Copy the 'request_token' parameter from the redirect URL.")

    req_token = input("\nEnter the request_token: ").strip()
    if req_token:
        try:
            token = broker.generate_session_from_token(req_token)
            print(f"\nSUCCESS! Session established. Access Token: {token[:6]}...{token[-4:]}")
        except Exception as e:
            print(f"Authentication failed: {e}")
    else:
        print("No request token provided. Exiting.")


def cmd_instruments(args):
    """Download and query instruments master."""
    print("Updating instruments master...")
    instrument_manager.load(force_refresh=args.refresh)
    if args.query:
        print(f"\nSearching for '{args.query}':")
        results = instrument_manager.search(args.query, limit=10)
        for inst in results:
            print(f"• Token: {inst.instrument_token:<8} | {inst.exchange:<5} | {inst.tradingsymbol:<15} | Lot: {inst.lot_size}")
    else:
        print("Instruments master is updated and cached.")


def cmd_positions(args):
    """Display active positions and margin summary."""
    broker = get_broker(args.mode)
    broker.authenticate()
    summary = broker.get_margins()
    positions = broker.get_positions()

    print("\n" + "=" * 60)
    print("ACCOUNT MARGIN SUMMARY")
    print("=" * 60)
    print(f"Available Cash: Rs. {summary.available_cash:,.2f}")
    print(f"Margin Used:    Rs. {summary.margin_used:,.2f}")
    print(f"Realized PnL:   Rs. {summary.realized_pnl:,.2f}")
    print(f"Unrealized PnL: Rs. {summary.unrealized_pnl:,.2f}")
    print(f"Net PnL:        Rs. {summary.net_pnl:,.2f}")

    print("\n" + "=" * 60)
    print(f"OPEN POSITIONS ({len(positions)})")
    print("=" * 60)
    if not positions:
        print("No active positions.")
    for p in positions:
        print(f"• {p.symbol:<12} | Qty: {p.quantity:<5} | Avg: Rs. {p.average_price:<8.2f} | LTP: Rs. {p.ltp:<8.2f} | PnL: Rs. {p.total_pnl:<8.2f}")


def cmd_kill_switch(args):
    """Emergency exit all positions and cancel orders."""
    print("\n⚠️  EMERGENCY KILL SWITCH ENGAGED ⚠️")
    confirm = input("Are you sure you want to SQUARE OFF ALL POSITIONS immediately? (yes/no): ").strip().lower()
    if confirm == "yes":
        broker = get_broker(args.mode)
        broker.authenticate()
        orders = broker.square_off_all()
        print(f"Square-off initiated. Orders sent: {len(orders)}")
    else:
        print("Aborted.")


def cmd_trade(args):
    """Start trading live or in paper mode."""
    mode = args.mode or settings.TRADING_MODE
    broker = get_broker(mode)
    risk_mgr = RiskManager()
    engine = ExecutionEngine(broker=broker, risk_manager=risk_mgr)

    symbols = [s.strip().upper() for s in args.symbols.split(",")]

    # Select strategy
    if args.strategy.lower() == "supertrend":
        strat = SupertrendEMAStrategy(symbols=symbols, timeframe_minutes=args.timeframe)
    elif args.strategy.lower() == "orb":
        strat = ORBStrategy(symbols=symbols)
    elif args.strategy.lower() == "straddle":
        strat = ShortStraddleStrategy(index_symbol=symbols[0])
    else:
        print(f"Unknown strategy: {args.strategy}")
        return

    engine.add_strategy(strat)
    engine.start()

    print("\n" + "=" * 60)
    print(f"ALGO TRADING ENGINE ACTIVE")
    print(f"Mode:     {mode.upper()}")
    print(f"Strategy: {strat.name}")
    print(f"Symbols:  {symbols}")
    print(f"Time:     {MarketHours.now_ist().strftime('%Y-%m-%d %H:%M:%S IST')}")
    print("=" * 60)
    print("Press Ctrl+C to stop trading gracefully.\n")

    try:
        if isinstance(broker, PaperBroker):
            print("Simulating market feed for paper trading...")
            # Simulate initial ticks to seed quotes
            for sym in symbols:
                quote = broker.get_quote(sym)
                ltp = quote.get("last_price", 1000.0)
                broker.update_quote(sym, ltp)

            # Keep alive loop
            while engine.is_running:
                time.sleep(1)
        else:
            # Live WebSocket Feed
            feed = MarketDataFeed()
            feed.initialize_websocket()
            tokens = []
            for s in symbols:
                inst = instrument_manager.get_by_symbol(s)
                if inst:
                    tokens.append(inst.instrument_token)
                    feed.register_aggregator(inst.instrument_token, args.timeframe)

            if tokens:
                feed.subscribe(tokens)
                feed.connect()

            while engine.is_running:
                time.sleep(1)

    except KeyboardInterrupt:
        print("\nShutdown requested by user.")
    finally:
        engine.stop()
        print("Engine stopped.")


def cmd_backtest(args):
    """Run historical backtest on a strategy."""
    symbols = [s.strip().upper() for s in args.symbols.split(",")]
    symbol = symbols[0]

    if args.strategy.lower() == "supertrend":
        strat = SupertrendEMAStrategy(symbols=[symbol], timeframe_minutes=args.timeframe)
    elif args.strategy.lower() == "orb":
        strat = ORBStrategy(symbols=[symbol])
    else:
        print(f"Unsupported backtest strategy: {args.strategy}")
        return

    broker = PaperBroker()
    to_date = datetime.now()
    from_date = to_date - timedelta(days=args.days)

    print(f"Fetching historical candles for {symbol} ({from_date.strftime('%Y-%m-%d')} to {to_date.strftime('%Y-%m-%d')})...")
    inst = instrument_manager.get_by_symbol(symbol)
    token = inst.instrument_token if inst else 0
    candles = broker.get_historical_data(token, from_date, to_date, interval="5m")

    if not candles:
        print("No historical candles available for backtesting.")
        return

    print(f"Running backtest across {len(candles)} candles...")
    backtester = Backtester(strategy=strat)
    metrics = backtester.run(symbol, candles)

    print("\n" + "=" * 60)
    print(f"BACKTEST RESULTS: {strat.name} ({symbol})")
    print("=" * 60)
    print(f"Total Trades:       {metrics.total_trades}")
    print(f"Winning Trades:     {metrics.winning_trades}")
    print(f"Losing Trades:      {metrics.losing_trades}")
    print(f"Win Rate:           {metrics.win_rate_pct:.2f}%")
    print(f"Total PnL:          Rs. {metrics.total_pnl:,.2f}")
    print(f"Profit Factor:      {metrics.profit_factor:.2f}")
    print(f"Max Drawdown:       {metrics.max_drawdown_pct:.2f}%")
    print(f"Sharpe Ratio:       {metrics.sharpe_ratio:.2f}")
    print(f"Average Trade PnL:  Rs. {metrics.average_trade_pnl:,.2f}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Zerodha Algo Trading System")
    subparsers = parser.add_subparsers(dest="command")

    # login
    p_login = subparsers.add_parser("login", help="Authenticate with Zerodha Kite")

    # instruments
    p_inst = subparsers.add_parser("instruments", help="Manage instruments master")
    p_inst.add_argument("-q", "--query", type=str, help="Search instrument by symbol or name")
    p_inst.add_argument("--refresh", action="store_true", help="Force download latest instruments CSV")

    # positions
    p_pos = subparsers.add_parser("positions", help="Show current positions and margins")
    p_pos.add_argument("--mode", type=str, default="paper", choices=["paper", "live"])

    # kill-switch
    p_kill = subparsers.add_parser("kill-switch", help="Emergency square-off all positions")
    p_kill.add_argument("--mode", type=str, default="paper", choices=["paper", "live"])

    # trade
    p_trade = subparsers.add_parser("trade", help="Run algorithmic trading engine")
    p_trade.add_argument("-s", "--strategy", type=str, default="supertrend", choices=["supertrend", "orb", "straddle"])
    p_trade.add_argument("--symbols", type=str, default="RELIANCE", help="Comma-separated symbols")
    p_trade.add_argument("-m", "--mode", type=str, default="paper", choices=["paper", "live"])
    p_trade.add_argument("-t", "--timeframe", type=int, default=5, help="Timeframe in minutes (e.g. 5)")

    # backtest
    p_bt = subparsers.add_parser("backtest", help="Run historical strategy backtest")
    p_bt.add_argument("-s", "--strategy", type=str, default="supertrend", choices=["supertrend", "orb"])
    p_bt.add_argument("--symbols", type=str, default="RELIANCE")
    p_bt.add_argument("-d", "--days", type=int, default=15, help="Number of historical days")
    p_bt.add_argument("-t", "--timeframe", type=int, default=5)

    args = parser.parse_args()
    if args.command == "login":
        cmd_login(args)
    elif args.command == "instruments":
        cmd_instruments(args)
    elif args.command == "positions":
        cmd_positions(args)
    elif args.command == "kill-switch":
        cmd_kill_switch(args)
    elif args.command == "trade":
        cmd_trade(args)
    elif args.command == "backtest":
        cmd_backtest(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
