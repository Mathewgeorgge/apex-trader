"""
Zerodha Algo Trader - Visual Web Dashboard & Controller.
Runs a local web server (http://localhost:8080) so you can control trading with a web browser.
Zero extra dependencies required (uses Python standard library).
"""

from __future__ import annotations
import json
import logging
import os
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

import core.compat  # noqa: F401
from broker.paper_broker import PaperBroker
from broker.zerodha_broker import ZerodhaBroker
from config.settings import settings
from engine.execution_engine import ExecutionEngine
from risk.risk_manager import RiskManager
from strategies.orb_strategy import ORBStrategy
from strategies.straddle_strategy import ShortStraddleStrategy
from strategies.supertrend_ema import SupertrendEMAStrategy

logger = logging.getLogger("Dashboard")

# Global State for Web Server
state = {
    "engine": None,
    "broker": None,
    "thread": None,
    "is_running": False,
    "strategy_name": "Supertrend_EMA",
    "symbols": ["RELIANCE"],
    "mode": "PAPER",
    "logs": [],
}


def log_message(msg: str):
    ts = time.strftime("%H:%M:%S")
    entry = f"[{ts}] {msg}"
    state["logs"].append(entry)
    if len(state["logs"]) > 100:
        state["logs"].pop(0)
    print(entry)


def get_broker(mode: str):
    if mode.upper() == "LIVE":
        settings.validate_keys()
        return ZerodhaBroker()
    return PaperBroker()


def background_trading_loop(engine, broker, symbols):
    log_message("Background trading worker loop started.")
    try:
        # Pre-seed quotes in paper mode
        if isinstance(broker, PaperBroker):
            for sym in symbols:
                quote = broker.get_quote(sym)
                ltp = quote.get("last_price", 1500.0)
                broker.update_quote(sym, ltp)

        while state["is_running"] and engine.is_running:
            time.sleep(1)
    except Exception as e:
        log_message(f"Trading loop error: {e}")
    finally:
        state["is_running"] = False
        log_message("Background trading worker stopped.")


class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress noisy HTTP request stdout logs
        pass

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            # Serve the pro-grade terminal HTML
            artifact_html = Path(r"C:\Users\simtadigital\.gemini\antigravity\brain\a782fe42-7ebc-4b6a-a594-956fa58ff206\trading_app.html")
            if artifact_html.exists():
                content = artifact_html.read_text(encoding="utf-8")
            else:
                content = HTML_DASHBOARD
            self.wfile.write(content.encode("utf-8"))
            return

        if path == "/api/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()

            broker = state["broker"] or PaperBroker()
            summary = broker.get_margins()
            positions = broker.get_positions()
            orders = broker.get_orders()

            data = {
                "is_running": state["is_running"],
                "strategy": state["strategy_name"],
                "symbols": state["symbols"],
                "mode": state["mode"],
                "cash": summary.available_cash,
                "margin_used": summary.margin_used,
                "realized_pnl": summary.realized_pnl,
                "unrealized_pnl": summary.unrealized_pnl,
                "net_pnl": summary.net_pnl,
                "positions": [
                    {
                        "symbol": p.symbol,
                        "qty": p.quantity,
                        "avg": p.average_price,
                        "ltp": p.ltp,
                        "pnl": p.total_pnl,
                    }
                    for p in positions
                ],
                "orders": [
                    {
                        "id": o.order_id,
                        "symbol": o.symbol,
                        "type": o.transaction_type.value,
                        "qty": o.quantity,
                        "price": o.average_price,
                        "status": o.status.value,
                        "time": o.created_at.strftime("%H:%M:%S"),
                    }
                    for o in reversed(orders[-15:])
                ],
                "logs": state["logs"][-25:],
            }
            self.wfile.write(json.dumps(data).encode("utf-8"))
            return

        self.send_error(404, "Not Found")

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
        payload = json.loads(body) if body else {}

        if path == "/api/start":
            if state["is_running"]:
                self._send_json({"status": "already_running"})
                return

            mode = payload.get("mode", "PAPER").upper()
            strategy_name = payload.get("strategy", "supertrend")
            symbols_str = payload.get("symbols", "RELIANCE")
            symbols = [s.strip().upper() for s in symbols_str.split(",") if s.strip()]

            broker = get_broker(mode)
            risk_mgr = RiskManager()
            engine = ExecutionEngine(broker=broker, risk_manager=risk_mgr)

            if strategy_name == "supertrend":
                strat = SupertrendEMAStrategy(symbols=symbols)
            elif strategy_name == "orb":
                strat = ORBStrategy(symbols=symbols)
            elif strategy_name == "straddle":
                strat = ShortStraddleStrategy(index_symbol=symbols[0])
            else:
                strat = SupertrendEMAStrategy(symbols=symbols)

            engine.add_strategy(strat)
            engine.start()

            state["engine"] = engine
            state["broker"] = broker
            state["strategy_name"] = strat.name
            state["symbols"] = symbols
            state["mode"] = mode
            state["is_running"] = True

            t = threading.Thread(target=background_trading_loop, args=(engine, broker, symbols), daemon=True)
            t.start()
            state["thread"] = t

            log_message(f"Bot started: {strat.name} on {symbols} in {mode} mode.")
            self._send_json({"status": "started"})
            return

        if path == "/api/stop":
            if state["engine"]:
                state["engine"].stop()
            state["is_running"] = False
            log_message("Bot stopped by user.")
            self._send_json({"status": "stopped"})
            return

        if path == "/api/kill":
            log_message("EMERGENCY KILL SWITCH CLICKED!")
            if state["broker"]:
                orders = state["broker"].square_off_all()
                log_message(f"Square-off initiated for {len(orders)} open positions.")
            if state["engine"]:
                state["engine"].stop()
            state["is_running"] = False
            self._send_json({"status": "killed"})
            return

        self.send_error(404, "Not Found")

    def _send_json(self, data: dict):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))


HTML_DASHBOARD = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Zerodha Algo Trader - Dashboard</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
  <style>
    body { background-color: #0b0f19; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    .card { background-color: #111827; border: 1px solid #1f2937; }
  </style>
</head>
<body class="text-gray-100 min-h-screen">
  <!-- Top Nav -->
  <header class="border-b border-gray-800 bg-gray-950 px-6 py-4 flex items-center justify-between">
    <div class="flex items-center space-x-3">
      <div class="bg-indigo-600 p-2 rounded-lg text-white">
        <i class="fa-solid fa-chart-line text-lg"></i>
      </div>
      <div>
        <h1 class="text-xl font-bold tracking-tight">Zerodha Algo Trader</h1>
        <p class="text-xs text-gray-400">Indian Equities & F&O Execution Platform</p>
      </div>
    </div>
    <div class="flex items-center space-x-4">
      <span id="badge-status" class="px-3 py-1 rounded-full text-xs font-semibold bg-gray-800 text-gray-400 border border-gray-700">
        <i class="fa-solid fa-circle text-[8px] mr-1 text-gray-500"></i> STOPPED
      </span>
      <button onclick="triggerKillSwitch()" class="bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded-lg text-sm font-semibold flex items-center shadow-lg transition">
        <i class="fa-solid fa-triangle-exclamation mr-2"></i> KILL SWITCH
      </button>
    </div>
  </header>

  <!-- Main Content -->
  <main class="p-6 max-w-7xl mx-auto space-y-6">

    <!-- KPI Summary Row -->
    <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
      <div class="card p-4 rounded-xl">
        <p class="text-xs font-medium text-gray-400">Available Capital</p>
        <p id="val-cash" class="text-2xl font-bold mt-1 text-white">Rs. 0.00</p>
        <span class="text-xs text-gray-500">Margin available</span>
      </div>
      <div class="card p-4 rounded-xl">
        <p class="text-xs font-medium text-gray-400">Margin Used</p>
        <p id="val-margin" class="text-2xl font-bold mt-1 text-white">Rs. 0.00</p>
        <span class="text-xs text-gray-500">In open positions</span>
      </div>
      <div class="card p-4 rounded-xl">
        <p class="text-xs font-medium text-gray-400">Realized PnL</p>
        <p id="val-realized" class="text-2xl font-bold mt-1 text-gray-200">Rs. 0.00</p>
        <span class="text-xs text-gray-500">Closed trades today</span>
      </div>
      <div class="card p-4 rounded-xl">
        <p class="text-xs font-medium text-gray-400">Net M2M PnL</p>
        <p id="val-netpnl" class="text-2xl font-bold mt-1 font-mono text-emerald-400">Rs. 0.00</p>
        <span class="text-xs text-gray-500">Live total profit/loss</span>
      </div>
    </div>

    <!-- Controls & Config -->
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
      
      <!-- Bot Controls Card -->
      <div class="card p-5 rounded-xl space-y-4">
        <h2 class="text-base font-semibold flex items-center text-white">
          <i class="fa-solid fa-sliders text-indigo-400 mr-2"></i> Strategy Controls
        </h2>
        
        <div>
          <label class="block text-xs font-medium text-gray-400 mb-1">Execution Mode</label>
          <select id="input-mode" class="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500">
            <option value="PAPER" selected>PAPER TRADING (Simulated - Zero Risk)</option>
            <option value="LIVE">LIVE TRADING (Zerodha Kite Connect)</option>
          </select>
        </div>

        <div>
          <label class="block text-xs font-medium text-gray-400 mb-1">Trading Strategy</label>
          <select id="input-strategy" class="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500">
            <option value="supertrend" selected>Supertrend (10, 3) + 20 EMA (Intraday Trend)</option>
            <option value="orb">Opening Range Breakout (ORB 15m) + VWAP</option>
            <option value="straddle">9:20 AM Short Straddle (Index Options)</option>
          </select>
        </div>

        <div>
          <label class="block text-xs font-medium text-gray-400 mb-1">Symbols (Comma-separated)</label>
          <input id="input-symbols" type="text" value="RELIANCE, TCS, INFY" class="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500" placeholder="e.g. RELIANCE, NIFTY 50">
        </div>

        <div class="pt-2 flex space-x-3">
          <button id="btn-start" onclick="startBot()" class="flex-1 bg-emerald-600 hover:bg-emerald-700 text-white font-semibold py-2.5 rounded-lg text-sm flex items-center justify-center transition">
            <i class="fa-solid fa-play mr-2"></i> Start Bot
          </button>
          <button id="btn-stop" onclick="stopBot()" class="flex-1 bg-gray-700 hover:bg-gray-600 text-white font-semibold py-2.5 rounded-lg text-sm flex items-center justify-center transition opacity-50 cursor-not-allowed" disabled>
            <i class="fa-solid fa-stop mr-2"></i> Stop Bot
          </button>
        </div>
      </div>

      <!-- Live Positions Card -->
      <div class="card p-5 rounded-xl space-y-4 lg:col-span-2">
        <h2 class="text-base font-semibold flex items-center text-white">
          <i class="fa-solid fa-layer-group text-blue-400 mr-2"></i> Open Positions
        </h2>
        <div class="overflow-x-auto">
          <table class="w-full text-left text-sm">
            <thead class="text-xs uppercase bg-gray-900/60 text-gray-400 border-b border-gray-800">
              <tr>
                <th class="py-2.5 px-3">Symbol</th>
                <th class="py-2.5 px-3">Qty</th>
                <th class="py-2.5 px-3">Avg Price</th>
                <th class="py-2.5 px-3">LTP</th>
                <th class="py-2.5 px-3">PnL</th>
              </tr>
            </thead>
            <tbody id="table-positions" class="divide-y divide-gray-800/50">
              <tr><td colspan="5" class="py-4 text-center text-gray-500 text-xs">No active positions.</td></tr>
            </tbody>
          </table>
        </div>
      </div>

    </div>

    <!-- Recent Orders & Activity Logs -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      
      <!-- Recent Orders -->
      <div class="card p-5 rounded-xl space-y-4">
        <h2 class="text-base font-semibold flex items-center text-white">
          <i class="fa-solid fa-receipt text-purple-400 mr-2"></i> Recent Order Fills
        </h2>
        <div class="overflow-x-auto">
          <table class="w-full text-left text-sm">
            <thead class="text-xs uppercase bg-gray-900/60 text-gray-400 border-b border-gray-800">
              <tr>
                <th class="py-2 px-3">Time</th>
                <th class="py-2 px-3">Type</th>
                <th class="py-2 px-3">Symbol</th>
                <th class="py-2 px-3">Qty</th>
                <th class="py-2 px-3">Fill Price</th>
              </tr>
            </thead>
            <tbody id="table-orders" class="divide-y divide-gray-800/50">
              <tr><td colspan="5" class="py-4 text-center text-gray-500 text-xs">No orders recorded yet.</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Live Logs Console -->
      <div class="card p-5 rounded-xl space-y-4">
        <h2 class="text-base font-semibold flex items-center text-white">
          <i class="fa-solid fa-terminal text-emerald-400 mr-2"></i> System Logs
        </h2>
        <div id="console-logs" class="bg-black/60 p-3 rounded-lg font-mono text-xs text-gray-300 h-64 overflow-y-auto space-y-1">
          <p class="text-gray-500">// Ready. Start the bot or check margins...</p>
        </div>
      </div>

    </div>

  </main>

  <script>
    async function updateStatus() {
      try {
        const res = await fetch('/api/status');
        const d = await res.json();

        // Update KPIs
        document.getElementById('val-cash').innerText = 'Rs. ' + d.cash.toLocaleString('en-IN', {minimumFractionDigits: 2});
        document.getElementById('val-margin').innerText = 'Rs. ' + d.margin_used.toLocaleString('en-IN', {minimumFractionDigits: 2});
        document.getElementById('val-realized').innerText = 'Rs. ' + d.realized_pnl.toLocaleString('en-IN', {minimumFractionDigits: 2});

        const netEl = document.getElementById('val-netpnl');
        netEl.innerText = 'Rs. ' + d.net_pnl.toLocaleString('en-IN', {minimumFractionDigits: 2});
        if (d.net_pnl > 0) {
          netEl.className = 'text-2xl font-bold mt-1 font-mono text-emerald-400';
        } else if (d.net_pnl < 0) {
          netEl.className = 'text-2xl font-bold mt-1 font-mono text-rose-400';
        } else {
          netEl.className = 'text-2xl font-bold mt-1 font-mono text-gray-200';
        }

        // Update Status Badge
        const badge = document.getElementById('badge-status');
        const btnStart = document.getElementById('btn-start');
        const btnStop = document.getElementById('btn-stop');

        if (d.is_running) {
          badge.className = 'px-3 py-1 rounded-full text-xs font-semibold bg-emerald-950 text-emerald-300 border border-emerald-800 animate-pulse';
          badge.innerHTML = '<i class="fa-solid fa-circle text-[8px] mr-1 text-emerald-400"></i> RUNNING (' + d.mode + ')';
          btnStart.disabled = true;
          btnStart.className = 'flex-1 bg-gray-700 text-gray-400 font-semibold py-2.5 rounded-lg text-sm flex items-center justify-center opacity-50 cursor-not-allowed';
          btnStop.disabled = false;
          btnStop.className = 'flex-1 bg-amber-600 hover:bg-amber-700 text-white font-semibold py-2.5 rounded-lg text-sm flex items-center justify-center transition';
        } else {
          badge.className = 'px-3 py-1 rounded-full text-xs font-semibold bg-gray-800 text-gray-400 border border-gray-700';
          badge.innerHTML = '<i class="fa-solid fa-circle text-[8px] mr-1 text-gray-500"></i> STOPPED';
          btnStart.disabled = false;
          btnStart.className = 'flex-1 bg-emerald-600 hover:bg-emerald-700 text-white font-semibold py-2.5 rounded-lg text-sm flex items-center justify-center transition';
          btnStop.disabled = true;
          btnStop.className = 'flex-1 bg-gray-700 text-gray-400 font-semibold py-2.5 rounded-lg text-sm flex items-center justify-center opacity-50 cursor-not-allowed';
        }

        // Positions table
        const posBody = document.getElementById('table-positions');
        if (d.positions.length === 0) {
          posBody.innerHTML = '<tr><td colspan="5" class="py-4 text-center text-gray-500 text-xs">No active positions.</td></tr>';
        } else {
          posBody.innerHTML = d.positions.map(p => {
            const pnlClass = p.pnl >= 0 ? 'text-emerald-400' : 'text-rose-400';
            return `<tr>
              <td class="py-2.5 px-3 font-semibold text-white">${p.symbol}</td>
              <td class="py-2.5 px-3 font-mono">${p.qty}</td>
              <td class="py-2.5 px-3 font-mono">Rs. ${p.avg.toFixed(2)}</td>
              <td class="py-2.5 px-3 font-mono">Rs. ${p.ltp.toFixed(2)}</td>
              <td class="py-2.5 px-3 font-mono font-semibold ${pnlClass}">Rs. ${p.pnl.toFixed(2)}</td>
            </tr>`;
          }).join('');
        }

        // Orders table
        const ordBody = document.getElementById('table-orders');
        if (d.orders.length === 0) {
          ordBody.innerHTML = '<tr><td colspan="5" class="py-4 text-center text-gray-500 text-xs">No orders recorded yet.</td></tr>';
        } else {
          ordBody.innerHTML = d.orders.map(o => {
            const typeClass = o.type === 'BUY' ? 'text-emerald-400' : 'text-rose-400';
            return `<tr>
              <td class="py-2 px-3 text-xs text-gray-400 font-mono">${o.time}</td>
              <td class="py-2 px-3 font-semibold ${typeClass}">${o.type}</td>
              <td class="py-2 px-3 font-medium text-white">${o.symbol}</td>
              <td class="py-2 px-3 font-mono">${o.qty}</td>
              <td class="py-2 px-3 font-mono">Rs. ${o.price.toFixed(2)}</td>
            </tr>`;
          }).join('');
        }

        // Logs console
        const logBox = document.getElementById('console-logs');
        if (d.logs.length > 0) {
          logBox.innerHTML = d.logs.map(l => `<p>${l}</p>`).join('');
          logBox.scrollTop = logBox.scrollHeight;
        }

      } catch (e) {
        console.error("Dashboard poll failed", e);
      }
    }

    async function startBot() {
      const mode = document.getElementById('input-mode').value;
      const strategy = document.getElementById('input-strategy').value;
      const symbols = document.getElementById('input-symbols').value;

      await fetch('/api/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode, strategy, symbols })
      });
      updateStatus();
    }

    async function stopBot() {
      await fetch('/api/stop', { method: 'POST' });
      updateStatus();
    }

    async function triggerKillSwitch() {
      if (confirm("Are you sure you want to trigger the EMERGENCY KILL SWITCH? This will square off all positions!")) {
        await fetch('/api/kill', { method: 'POST' });
        updateStatus();
      }
    }

    // Refresh every 1.5 seconds
    setInterval(updateStatus, 1500);
    updateStatus();
  </script>
</body>
</html>
"""


def run_server(port: int = 8080):
    server_address = ("127.0.0.1", port)
    httpd = HTTPServer(server_address, DashboardHandler)
    url = f"http://localhost:{port}"
    print("=" * 60)
    print(f"ZERODHA ALGO TRADER - WEB DASHBOARD RUNNING")
    print(f"Open this link in your browser:")
    print(f"👉  {url}")
    print("=" * 60)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down dashboard server...")
        httpd.server_close()


if __name__ == "__main__":
    run_server()
