"""
Zerodha Algo Trader - Native Windows Desktop Application.
Zero terminal needed! Just double-click to launch a graphical trading interface.
"""

from __future__ import annotations
import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

import core.compat  # noqa: F401
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

from broker.paper_broker import PaperBroker
from broker.zerodha_broker import ZerodhaBroker
from config.settings import settings
from engine.execution_engine import ExecutionEngine
from risk.risk_manager import RiskManager
from strategies.orb_strategy import ORBStrategy
from strategies.straddle_strategy import ShortStraddleStrategy
from strategies.supertrend_ema import SupertrendEMAStrategy


class AlgoTraderApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Zerodha Algo Trader - India Equities & F&O")
        self.root.geometry("980x720")
        self.root.minsize(850, 600)
        self.root.configure(bg="#0f172a")

        # Styling
        self.style = ttk.Style()
        self.style.theme_use("clam")

        # Custom colors
        self.bg_color = "#0f172a"
        self.card_bg = "#1e293b"
        self.text_color = "#f8fafc"
        self.accent_green = "#10b981"
        self.accent_red = "#ef4444"
        self.accent_blue = "#3b82f6"

        # Engine & Trading State
        self.broker = PaperBroker()
        self.engine = None
        self.worker_thread = None
        self.is_running = False

        self._setup_ui()
        self._start_poll_timer()

    def _setup_ui(self):
        # 1. Header Frame
        header = tk.Frame(self.root, bg="#020617", height=65, padx=20)
        header.pack(fill=tk.X, side=tk.TOP)

        title_lbl = tk.Label(
            header,
            text="⚡ Zerodha Algo Trader",
            font=("Segoe UI", 16, "bold"),
            fg="#f8fafc",
            bg="#020617",
        )
        title_lbl.pack(side=tk.LEFT, pady=12)

        self.status_badge = tk.Label(
            header,
            text="● STOPPED",
            font=("Segoe UI", 10, "bold"),
            fg="#94a3b8",
            bg="#1e293b",
            padx=12,
            pady=4,
        )
        self.status_badge.pack(side=tk.RIGHT, pady=14)

        # 2. KPI Cards Row
        kpi_frame = tk.Frame(self.root, bg=self.bg_color, padx=15, pady=10)
        kpi_frame.pack(fill=tk.X)

        self.card_cash = self._create_kpi_card(kpi_frame, "Available Capital", "Rs. 100,000.00", 0)
        self.card_margin = self._create_kpi_card(kpi_frame, "Margin Used", "Rs. 0.00", 1)
        self.card_realized = self._create_kpi_card(kpi_frame, "Realized PnL", "Rs. 0.00", 2)
        self.card_net_pnl = self._create_kpi_card(kpi_frame, "Net M2M PnL", "Rs. 0.00", 3, is_highlight=True)

        # 3. Main Split View (Left: Controls, Right: Positions & Orders)
        body_frame = tk.Frame(self.root, bg=self.bg_color, padx=15, pady=5)
        body_frame.pack(fill=tk.BOTH, expand=True)

        # Left Column: Configuration & Actions
        left_panel = tk.LabelFrame(
            body_frame,
            text=" Strategy & Control Panel ",
            font=("Segoe UI", 11, "bold"),
            fg="#cbd5e1",
            bg=self.card_bg,
            padx=15,
            pady=15,
        )
        left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))

        # Mode Selection
        tk.Label(left_panel, text="Starting Capital (Rs.):", font=("Segoe UI", 9, "bold"), fg="#94a3b8", bg=self.card_bg).pack(anchor=tk.W, pady=(5, 2))
        self.capital_entry = tk.Entry(left_panel, font=("Segoe UI", 10), bg="#0f172a", fg="#f8fafc", insertbackground="white", width=30)
        self.capital_entry.insert(0, "5000")
        self.capital_entry.pack(anchor=tk.W, pady=(0, 10))

        tk.Label(left_panel, text="Trading Mode:", font=("Segoe UI", 9, "bold"), fg="#94a3b8", bg=self.card_bg).pack(anchor=tk.W, pady=(5, 2))
        self.mode_var = tk.StringVar(value="PAPER")
        mode_cb = ttk.Combobox(left_panel, textvariable=self.mode_var, values=["PAPER", "LIVE"], state="readonly", width=28)
        mode_cb.pack(anchor=tk.W, pady=(0, 10))

        # Strategy Selection
        tk.Label(left_panel, text="Strategy:", font=("Segoe UI", 9, "bold"), fg="#94a3b8", bg=self.card_bg).pack(anchor=tk.W, pady=(5, 2))
        self.strategy_var = tk.StringVar(value="Supertrend + EMA")
        strat_cb = ttk.Combobox(
            left_panel,
            textvariable=self.strategy_var,
            values=["Supertrend + EMA", "Opening Range Breakout (ORB)", "9:20 AM Short Straddle"],
            state="readonly",
            width=28,
        )
        strat_cb.pack(anchor=tk.W, pady=(0, 10))

        # Symbols Input
        tk.Label(left_panel, text="Trading Symbols (Comma separated):", font=("Segoe UI", 9, "bold"), fg="#94a3b8", bg=self.card_bg).pack(anchor=tk.W, pady=(5, 2))
        self.symbols_entry = tk.Entry(left_panel, font=("Segoe UI", 10), bg="#0f172a", fg="#f8fafc", insertbackground="white", width=30)
        self.symbols_entry.insert(0, "RELIANCE, TCS")
        self.symbols_entry.pack(anchor=tk.W, pady=(0, 15))

        # Action Buttons
        self.btn_start = tk.Button(
            left_panel,
            text="▶  START TRADING",
            font=("Segoe UI", 11, "bold"),
            bg="#10b981",
            fg="white",
            activebackground="#059669",
            cursor="hand2",
            height=2,
            command=self.start_trading,
        )
        self.btn_start.pack(fill=tk.X, pady=(5, 6))

        self.btn_stop = tk.Button(
            left_panel,
            text="⏹  STOP BOT",
            font=("Segoe UI", 10, "bold"),
            bg="#475569",
            fg="white",
            state=tk.DISABLED,
            command=self.stop_trading,
        )
        self.btn_stop.pack(fill=tk.X, pady=(0, 10))

        # Kite API Setup Button
        btn_kite_setup = tk.Button(
            left_panel,
            text="🔑  Connect Zerodha Kite API",
            font=("Segoe UI", 9, "bold"),
            bg="#3b82f6",
            fg="white",
            activebackground="#2563eb",
            cursor="hand2",
            command=self.open_kite_setup_dialog,
        )
        btn_kite_setup.pack(fill=tk.X, pady=(0, 15))

        # Emergency Kill Switch
        btn_kill = tk.Button(
            left_panel,
            text="🚨  EMERGENCY KILL SWITCH",
            font=("Segoe UI", 10, "bold"),
            bg="#dc2626",
            fg="white",
            activebackground="#b91c1c",
            cursor="hand2",
            command=self.kill_switch,
        )
        btn_kill.pack(fill=tk.X, side=tk.BOTTOM, pady=(15, 0))

        # Right Column: Notebook with Positions, Orders, and Logs
        right_panel = tk.Frame(body_frame, bg=self.bg_color)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        notebook = ttk.Notebook(right_panel)
        notebook.pack(fill=tk.BOTH, expand=True)

        # Tab 1: Positions
        tab_pos = tk.Frame(notebook, bg=self.card_bg)
        notebook.add(tab_pos, text="  Open Positions  ")
        self._setup_positions_table(tab_pos)

        # Tab 2: Orders
        tab_orders = tk.Frame(notebook, bg=self.card_bg)
        notebook.add(tab_orders, text="  Order Fills  ")
        self._setup_orders_table(tab_orders)

        # Tab 3: System Logs
        tab_logs = tk.Frame(notebook, bg=self.card_bg)
        notebook.add(tab_logs, text="  Activity Log  ")
        self.log_box = scrolledtext.ScrolledText(tab_logs, bg="#020617", fg="#94a3b8", font=("Consolas", 9), insertbackground="white")
        self.log_box.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.log("Application started. Ready to trade.")

    def _create_kpi_card(self, parent, title, default_val, col, is_highlight=False):
        card = tk.Frame(parent, bg=self.card_bg, padx=12, pady=10, relief=tk.FLAT)
        card.grid(row=0, column=col, sticky="nsew", padx=5)
        parent.grid_columnconfigure(col, weight=1)

        t_lbl = tk.Label(card, text=title, font=("Segoe UI", 8), fg="#94a3b8", bg=self.card_bg)
        t_lbl.pack(anchor=tk.W)

        val_color = "#34d399" if is_highlight else "#f8fafc"
        v_lbl = tk.Label(card, text=default_val, font=("Segoe UI", 13, "bold"), fg=val_color, bg=self.card_bg)
        v_lbl.pack(anchor=tk.W, pady=(3, 0))
        return v_lbl

    def _setup_positions_table(self, parent):
        cols = ("symbol", "qty", "avg", "ltp", "pnl")
        self.tree_pos = ttk.Treeview(parent, columns=cols, show="headings", height=8)
        self.tree_pos.heading("symbol", text="Symbol")
        self.tree_pos.heading("qty", text="Quantity")
        self.tree_pos.heading("avg", text="Avg Buy (Rs.)")
        self.tree_pos.heading("ltp", text="LTP (Rs.)")
        self.tree_pos.heading("pnl", text="PnL (Rs.)")

        for c in cols:
            self.tree_pos.column(c, anchor=tk.CENTER, width=110)

        self.tree_pos.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

    def _setup_orders_table(self, parent):
        cols = ("time", "type", "symbol", "qty", "price", "status")
        self.tree_orders = ttk.Treeview(parent, columns=cols, show="headings", height=8)
        self.tree_orders.heading("time", text="Time")
        self.tree_orders.heading("type", text="Action")
        self.tree_orders.heading("symbol", text="Symbol")
        self.tree_orders.heading("qty", text="Qty")
        self.tree_orders.heading("price", text="Price (Rs.)")
        self.tree_orders.heading("status", text="Status")

        for c in cols:
            self.tree_orders.column(c, anchor=tk.CENTER, width=95)

        self.tree_orders.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

    def open_kite_setup_dialog(self):
        """Popup window to easily enter Kite API Key & Secret without editing code."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Zerodha Kite Connect Setup")
        dialog.geometry("460x420")
        dialog.configure(bg="#0f172a")
        dialog.resizable(False, False)

        tk.Label(dialog, text="🔑 Zerodha Kite API Setup", font=("Segoe UI", 13, "bold"), fg="#f8fafc", bg="#0f172a").pack(pady=(15, 5))
        tk.Label(dialog, text="Enter your Kite Developer credentials below. They stay 100% private.", font=("Segoe UI", 8), fg="#94a3b8", bg="#0f172a").pack(pady=(0, 15))

        form = tk.Frame(dialog, bg="#0f172a", padx=25)
        form.pack(fill=tk.BOTH, expand=True)

        # Fields
        tk.Label(form, text="API Key (from developers.kite.trade):", font=("Segoe UI", 9, "bold"), fg="#cbd5e1", bg="#0f172a").pack(anchor=tk.W)
        e_apikey = tk.Entry(form, font=("Segoe UI", 10), bg="#1e293b", fg="white", insertbackground="white", width=42)
        e_apikey.insert(0, settings.KITE_API_KEY or "")
        e_apikey.pack(pady=(2, 10))

        tk.Label(form, text="API Secret:", font=("Segoe UI", 9, "bold"), fg="#cbd5e1", bg="#0f172a").pack(anchor=tk.W)
        e_secret = tk.Entry(form, font=("Segoe UI", 10), bg="#1e293b", fg="white", insertbackground="white", width=42, show="*")
        e_secret.insert(0, settings.KITE_API_SECRET or "")
        e_secret.pack(pady=(2, 10))

        tk.Label(form, text="Zerodha User ID (e.g. AB1234):", font=("Segoe UI", 9, "bold"), fg="#cbd5e1", bg="#0f172a").pack(anchor=tk.W)
        e_uid = tk.Entry(form, font=("Segoe UI", 10), bg="#1e293b", fg="white", insertbackground="white", width=42)
        e_uid.insert(0, settings.KITE_USER_ID or "")
        e_uid.pack(pady=(2, 15))

        def save_and_close():
            api_k = e_apikey.get().strip()
            api_s = e_secret.get().strip()
            u_id = e_uid.get().strip().upper()

            if not api_k or not api_s:
                messagebox.showwarning("Incomplete", "Please enter both API Key and API Secret.", parent=dialog)
                return

            # Save to .env
            env_path = PROJECT_ROOT / ".env"
            env_content = f"""# Zerodha Algo Trader Configuration
TRADING_MODE=LIVE
KITE_API_KEY={api_k}
KITE_API_SECRET={api_s}
KITE_USER_ID={u_id}
MAX_DAILY_LOSS=500.0
MAX_CAPITAL_PER_TRADE=5000.0
MAX_TRADES_PER_DAY=3
DEFAULT_PRODUCT=MIS
"""
            with open(env_path, "w") as f:
                f.write(env_content)

            settings.KITE_API_KEY = api_k
            settings.KITE_API_SECRET = api_s
            settings.KITE_USER_ID = u_id

            self.mode_var.set("LIVE")
            self.log("Zerodha Kite API credentials saved successfully. Switched to LIVE mode.")
            messagebox.showinfo("Saved!", "Credentials saved securely to .env!\nYou can now start LIVE trading.", parent=dialog)
            dialog.destroy()

        btn_save = tk.Button(
            dialog,
            text="💾 Save & Connect to Zerodha",
            font=("Segoe UI", 11, "bold"),
            bg="#10b981",
            fg="white",
            cursor="hand2",
            command=save_and_close,
            height=2,
        )
        btn_save.pack(fill=tk.X, padx=25, pady=(0, 20))

    def log(self, text: str):
        now = datetime.now().strftime("%H:%M:%S")
        self.log_box.insert(tk.END, f"[{now}] {text}\n")
        self.log_box.see(tk.END)

    def start_trading(self):
        if self.is_running:
            return

        mode = self.mode_var.get()
        strategy_label = self.strategy_var.get()
        symbols = [s.strip().upper() for s in self.symbols_entry.get().split(",") if s.strip()]

        if not symbols:
            messagebox.showwarning("Warning", "Please enter at least one trading symbol!")
            return

        # Prepare Broker
        if mode == "LIVE":
            try:
                settings.validate_keys()
                self.broker = ZerodhaBroker()
                self.broker.authenticate()
            except Exception as e:
                messagebox.showerror("Broker Error", f"Failed to authenticate with Zerodha: {e}")
                return
        else:
            self.broker = PaperBroker()

        # Select Strategy
        if "Supertrend" in strategy_label:
            strat = SupertrendEMAStrategy(symbols=symbols)
        elif "ORB" in strategy_label:
            strat = ORBStrategy(symbols=symbols)
        else:
            strat = ShortStraddleStrategy(index_symbol=symbols[0])

        risk_mgr = RiskManager()
        self.engine = ExecutionEngine(broker=self.broker, risk_manager=risk_mgr)
        self.engine.add_strategy(strat)
        self.engine.start()

        self.is_running = True
        self.btn_start.config(state=tk.DISABLED, bg="#475569")
        self.btn_stop.config(state=tk.NORMAL, bg="#f59e0b")
        self.status_badge.config(text=f"● RUNNING ({mode})", fg="#34d399", bg="#064e3b")

        self.log(f"Trading started in {mode} mode on {symbols} using {strat.name}.")

        # Background simulator / tick worker
        self.worker_thread = threading.Thread(target=self._run_loop, args=(symbols,), daemon=True)
        self.worker_thread.start()

    def _run_loop(self, symbols):
        # Seed initial quotes for paper simulation
        if isinstance(self.broker, PaperBroker):
            for s in symbols:
                quote = self.broker.get_quote(s)
                ltp = quote.get("last_price", 1500.0)
                self.broker.update_quote(s, ltp)

        while self.is_running and self.engine.is_running:
            time.sleep(1)

    def stop_trading(self):
        if self.engine:
            self.engine.stop()
        self.is_running = False
        self.btn_start.config(state=tk.NORMAL, bg="#10b981")
        self.btn_stop.config(state=tk.DISABLED, bg="#475569")
        self.status_badge.config(text="● STOPPED", fg="#94a3b8", bg="#1e293b")
        self.log("Bot stopped by user.")

    def kill_switch(self):
        confirm = messagebox.askyesno(
            "EMERGENCY KILL SWITCH",
            "Are you sure you want to trigger the EMERGENCY KILL SWITCH?\n\nThis will immediately square off all open positions and cancel orders!",
            icon="warning",
        )
        if confirm:
            if self.broker:
                orders = self.broker.square_off_all()
                self.log(f"Emergency square-off executed. Orders placed: {len(orders)}")
            self.stop_trading()
            messagebox.showinfo("Kill Switch Activated", "All positions squared off successfully.")

    def _start_poll_timer(self):
        self._refresh_ui()
        self.root.after(1500, self._start_poll_timer)

    def _refresh_ui(self):
        if not self.broker:
            return

        try:
            summary = self.broker.get_margins()
            positions = self.broker.get_positions()
            orders = self.broker.get_orders()

            self.card_cash.config(text=f"Rs. {summary.available_cash:,.2f}")
            self.card_margin.config(text=f"Rs. {summary.margin_used:,.2f}")
            self.card_realized.config(text=f"Rs. {summary.realized_pnl:,.2f}")

            net = summary.net_pnl
            pnl_color = "#34d399" if net >= 0 else "#f87171"
            self.card_net_pnl.config(text=f"Rs. {net:,.2f}", fg=pnl_color)

            # Refresh Positions Table
            for item in self.tree_pos.get_children():
                self.tree_pos.delete(item)
            for p in positions:
                self.tree_pos.insert("", tk.END, values=(p.symbol, p.quantity, f"{p.average_price:.2f}", f"{p.ltp:.2f}", f"{p.total_pnl:.2f}"))

            # Refresh Orders Table
            for item in self.tree_orders.get_children():
                self.tree_orders.delete(item)
            for o in reversed(orders[-15:]):
                t_str = o.created_at.strftime("%H:%M:%S")
                self.tree_orders.insert("", tk.END, values=(t_str, o.transaction_type.value, o.symbol, o.quantity, f"{o.average_price:.2f}", o.status.value))

        except Exception:
            pass


def main():
    root = tk.Tk()
    app = AlgoTraderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
