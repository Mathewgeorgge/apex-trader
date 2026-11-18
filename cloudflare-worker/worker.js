/**
 * ApexTrader Pro - Read-Only Zerodha Kite Connect Live Data Relay
 * Hosted on Cloudflare Workers FREE Tier (100,000 req/day free, $0 cost)
 * STRICTLY READ-ONLY: Never places, modifies, or cancels real Zerodha orders.
 * Pulls 100% real live NSE Equity, Index, F&O Option prices, Level 2 Depth,
 * and Historical 1m Candlesticks for safe Paper Mode trading during market hours.
 */

const ALLOWED_ORIGINS = [
  "https://mathewgeorgge.github.io",
  "http://localhost:3000",
  "http://localhost:8080",
  "http://127.0.0.1:8080"
];

const NSE_EQUITY_MAP = {
  "NIFTY 50": "NSE:NIFTY 50",
  "BANK NIFTY": "NSE:NIFTY BANK",
  "INDIA VIX": "NSE:INDIA VIX",
  "RELIANCE": "NSE:RELIANCE",
  "HDFCBANK": "NSE:HDFCBANK",
  "ICICIBANK": "NSE:ICICIBANK",
  "SBIN": "NSE:SBIN",
  "KOTAKBANK": "NSE:KOTAKBANK",
  "AXISBANK": "NSE:AXISBANK",
  "TCS": "NSE:TCS",
  "INFY": "NSE:INFY",
  "WIPRO": "NSE:WIPRO",
  "TATAMOTORS": "NSE:TATAMOTORS",
  "M&M": "NSE:M&M",
  "MARUTI": "NSE:MARUTI",
  "BHARTIARTL": "NSE:BHARTIARTL",
  "ITC": "NSE:ITC",
  "HINDUNILVR": "NSE:HINDUNILVR",
  "TATASTEEL": "NSE:TATASTEEL",
  "LT": "NSE:LT",
  "SUNPHARMA": "NSE:SUNPHARMA"
};

// In-isolate memory cache for NFO instrument master (zero paid KV needed!)
let nfoCache = { loadedAt: 0, contracts: [] };

function corsHeaders(request) {
  const origin = request.headers.get("Origin") || "";
  const allowOrigin = ALLOWED_ORIGINS.includes(origin) ? origin : "https://mathewgeorgge.github.io";
  return {
    "Access-Control-Allow-Origin": allowOrigin,
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Kite-Token",
    "Access-Control-Max-Age": "86400",
    "Content-Type": "application/json"
  };
}

function jsonResponse(request, data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: corsHeaders(request) });
}

async function sha256Hex(str) {
  const buf = new TextEncoder().encode(str);
  const hash = await crypto.subtle.digest("SHA-256", buf);
  return [...new Uint8Array(hash)].map(b => b.toString(16).padStart(2, "0")).join("");
}

function extractToken(request) {
  const hdr = request.headers.get("X-Kite-Token") || request.headers.get("Authorization") || "";
  return hdr.replace(/^Bearer\s+/i, "").trim();
}

async function loadNfoInstruments(apiKey, accessToken) {
  const now = Date.now();
  // Refresh NFO contract master every 4 hours
  if (nfoCache.contracts.length > 0 && now - nfoCache.loadedAt < 4 * 3600 * 1000) {
    return nfoCache.contracts;
  }
  const resp = await fetch("https://api.kite.trade/instruments/NFO", {
    headers: {
      "X-Kite-Version": "3",
      "Authorization": `token ${apiKey}:${accessToken}`
    }
  });
  if (!resp.ok) return nfoCache.contracts;
  const csv = await resp.text();
  const lines = csv.split("\n");
  const todayStr = new Date(Date.now() + 5.5 * 3600 * 1000).toISOString().slice(0, 10);
  const parsed = [];

  for (let i = 1; i < lines.length; i++) {
    const line = lines[i];
    if (!line) continue;
    // Fast pre-filter for NIFTY, BANKNIFTY, RELIANCE before splitting
    if (!line.includes(",NIFTY") && !line.includes(",BANKNIFTY") && !line.includes(",RELIANCE")) continue;
    const cols = line.split(",");
    if (cols.length < 10) continue;
    const name = (cols[3] || "").replace(/"/g, "");
    if (name !== "NIFTY" && name !== "BANKNIFTY" && name !== "RELIANCE") continue;
    const expiry = (cols[5] || "").replace(/"/g, "");
    if (!expiry || expiry < todayStr) continue;
    parsed.push({
      token: cols[0],
      tradingsymbol: (cols[2] || "").replace(/"/g, ""),
      name,
      expiry,
      strike: parseFloat(cols[6]) || 0,
      lot_size: parseInt(cols[8], 10) || 1,
      instrument_type: (cols[9] || "").replace(/"/g, "")
    });
  }

  parsed.sort((a, b) => a.expiry.localeCompare(b.expiry));
  nfoCache = { loadedAt: now, contracts: parsed };
  return parsed;
}

function resolveNearestFnoContracts(contracts, niftySpot, bankNiftySpot, relianceSpot) {
  const result = {};
  if (!contracts || contracts.length === 0) return result;

  const pickOption = (underlying, strikeStep, spot, offsetSteps, optType) => {
    const targetStrike = Math.round(spot / strikeStep) * strikeStep + offsetSteps * strikeStep;
    const matches = contracts.filter(c => c.name === underlying && c.instrument_type === optType && Math.abs(c.strike - targetStrike) < 1);
    return matches[0] || null;
  };
  const pickFuture = (underlying) => {
    const matches = contracts.filter(c => c.name === underlying && c.instrument_type === "FUT");
    return matches[0] || null;
  };

  if (niftySpot > 0) {
    const nAtmCe = pickOption("NIFTY", 50, niftySpot, 0, "CE");
    const nAtmPe = pickOption("NIFTY", 50, niftySpot, 0, "PE");
    const nOtmCe = pickOption("NIFTY", 50, niftySpot, 2, "CE");
    const nOtmPe = pickOption("NIFTY", 50, niftySpot, -2, "PE");
    const nFut = pickFuture("NIFTY");
    if (nAtmCe) result["NIFTY_ATM_CE"] = nAtmCe;
    if (nAtmPe) result["NIFTY_ATM_PE"] = nAtmPe;
    if (nOtmCe) result["NIFTY_OTM_CE"] = nOtmCe;
    if (nOtmPe) result["NIFTY_OTM_PE"] = nOtmPe;
    if (nFut) result["NIFTY FUT"] = nFut;
  }
  if (bankNiftySpot > 0) {
    const bnAtmCe = pickOption("BANKNIFTY", 100, bankNiftySpot, 0, "CE");
    const bnAtmPe = pickOption("BANKNIFTY", 100, bankNiftySpot, 0, "PE");
    const bnFut = pickFuture("BANKNIFTY");
    if (bnAtmCe) result["BANKNIFTY_ATM_CE"] = bnAtmCe;
    if (bnAtmPe) result["BANKNIFTY_ATM_PE"] = bnAtmPe;
    if (bnFut) result["BANKNIFTY FUT"] = bnFut;
  }
  if (relianceSpot > 0) {
    const relCe = pickOption("RELIANCE", 20, relianceSpot, 0, "CE");
    if (relCe) result["RELIANCE_ATM_CE"] = relCe;
  }

  return result;
}

function formatISTDate(dateObj) {
  const ist = new Date(dateObj.getTime() + 5.5 * 3600 * 1000);
  const y = ist.getUTCFullYear();
  const m = String(ist.getUTCMonth() + 1).padStart(2, "0");
  const d = String(ist.getUTCDate()).padStart(2, "0");
  const hh = String(ist.getUTCHours()).padStart(2, "0");
  const mm = String(ist.getUTCMinutes()).padStart(2, "0");
  const ss = String(ist.getUTCSeconds()).padStart(2, "0");
  return `${y}-${m}-${d} ${hh}:${mm}:${ss}`;
}

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders(request) });
    }

    const url = new URL(request.url);
    const apiKey = env.KITE_API_KEY;
    const apiSecret = env.KITE_API_SECRET;

    if (url.pathname === "/" || url.pathname === "/health") {
      return jsonResponse(request, {
        ok: true,
        service: "ApexTrader Pro Read-Only Zerodha Kite Relay",
        mode: "READ_ONLY_PAPER_SAFE",
        configured: Boolean(apiKey && apiSecret)
      });
    }

    if (!apiKey || !apiSecret) {
      return jsonResponse(request, { error: "Worker secrets KITE_API_KEY / KITE_API_SECRET not configured." }, 500);
    }

    // 1. Exchange daily request_token -> real Kite access_token (server-side SHA-256)
    if (url.pathname === "/api/session" && request.method === "POST") {
      try {
        const body = await request.json();
        const requestToken = (body.request_token || "").trim();
        if (!requestToken) {
          return jsonResponse(request, { error: "Missing request_token" }, 400);
        }

        const checksum = await sha256Hex(`${apiKey}${requestToken}${apiSecret}`);
        const form = new URLSearchParams();
        form.set("api_key", apiKey);
        form.set("request_token", requestToken);
        form.set("checksum", checksum);

        const kiteResp = await fetch("https://api.kite.trade/session/token", {
          method: "POST",
          headers: {
            "X-Kite-Version": "3",
            "Content-Type": "application/x-www-form-urlencoded"
          },
          body: form.toString()
        });
        const kiteJson = await kiteResp.json();
        if (!kiteResp.ok || kiteJson.status !== "success") {
          return jsonResponse(request, { error: kiteJson.message || "Kite session exchange failed", details: kiteJson }, 401);
        }

        return jsonResponse(request, {
          status: "success",
          access_token: kiteJson.data.access_token,
          user_id: kiteJson.data.user_id,
          user_name: kiteJson.data.user_name,
          login_time: kiteJson.data.login_time
        });
      } catch (err) {
        return jsonResponse(request, { error: String(err) }, 500);
      }
    }

    // All market data routes require a valid Kite access_token
    const accessToken = extractToken(request);
    if (!accessToken) {
      return jsonResponse(request, { error: "Missing X-Kite-Token header. Complete 1-Click Kite Login first." }, 401);
    }

    // 2. Pull Real Live NSE Share + Dynamic Active-Expiry F&O Option Quotes & Level 2 Depth
    if (url.pathname === "/api/quotes" && request.method === "GET") {
      try {
        const eqParams = Object.values(NSE_EQUITY_MAP).map(s => `i=${encodeURIComponent(s)}`).join("&");
        const eqResp = await fetch(`https://api.kite.trade/quote?${eqParams}`, {
          headers: {
            "X-Kite-Version": "3",
            "Authorization": `token ${apiKey}:${accessToken}`
          }
        });
        const eqJson = await eqResp.json();
        if (!eqResp.ok || eqJson.status !== "success") {
          return jsonResponse(request, { error: eqJson.message || "Failed to pull NSE quotes", kiteStatus: eqResp.status }, eqResp.status || 502);
        }

        const eqData = eqJson.data || {};
        const equities = {};
        for (const [uiSym, kiteSym] of Object.entries(NSE_EQUITY_MAP)) {
          const q = eqData[kiteSym];
          if (!q) continue;
          equities[uiSym] = {
            tradingsymbol: kiteSym,
            token: q.instrument_token,
            ltp: q.last_price,
            open: q.ohlc?.open || q.last_price,
            high: q.ohlc?.high || q.last_price,
            low: q.ohlc?.low || q.last_price,
            prevClose: q.ohlc?.close || q.last_price,
            volume: q.volume || 0,
            depth: q.depth || null
          };
        }

        // Resolve real current-expiry F&O options & futures dynamically around live spot
        const niftySpot = equities["NIFTY 50"]?.ltp || 0;
        const bnSpot = equities["BANK NIFTY"]?.ltp || 0;
        const relSpot = equities["RELIANCE"]?.ltp || 0;

        let fno = {};
        try {
          const nfoList = await loadNfoInstruments(apiKey, accessToken);
          const resolved = resolveNearestFnoContracts(nfoList, niftySpot, bnSpot, relSpot);
          const fnoEntries = Object.entries(resolved);
          if (fnoEntries.length > 0) {
            const fnoParams = fnoEntries.map(([, c]) => `i=${encodeURIComponent("NFO:" + c.tradingsymbol)}`).join("&");
            const fnoResp = await fetch(`https://api.kite.trade/quote?${fnoParams}`, {
              headers: {
                "X-Kite-Version": "3",
                "Authorization": `token ${apiKey}:${accessToken}`
              }
            });
            const fnoJson = await fnoResp.json();
            if (fnoResp.ok && fnoJson.status === "success" && fnoJson.data) {
              for (const [slotKey, contract] of fnoEntries) {
                const q = fnoJson.data[`NFO:${contract.tradingsymbol}`];
                if (!q) continue;
                const displayLabel = contract.instrument_type === "FUT"
                  ? slotKey
                  : `${contract.name} ${contract.strike} ${contract.instrument_type}`;
                fno[slotKey] = {
                  slotKey,
                  displayLabel,
                  tradingsymbol: contract.tradingsymbol,
                  expiry: contract.expiry,
                  strike: contract.strike,
                  lot: contract.lot_size,
                  token: q.instrument_token,
                  ltp: q.last_price,
                  open: q.ohlc?.open || q.last_price,
                  high: q.ohlc?.high || q.last_price,
                  low: q.ohlc?.low || q.last_price,
                  prevClose: q.ohlc?.close || q.last_price,
                  volume: q.volume || 0,
                  oi: q.oi || 0,
                  depth: q.depth || null
                };
              }
            }
          }
        } catch (_fnoErr) {
          // Non-fatal: still return real equity quotes even if NFO master temporarily fails
        }

        return jsonResponse(request, {
          status: "success",
          timestamp: Date.now(),
          equities,
          fno
        });
      } catch (err) {
        return jsonResponse(request, { error: String(err) }, 500);
      }
    }

    // 3. Pull Real 1-Minute Intraday Historical Candles (Uses Paid Kite Historical API)
    if (url.pathname === "/api/historical" && request.method === "GET") {
      try {
        const token = url.searchParams.get("token");
        const interval = url.searchParams.get("interval") || "minute";
        if (!token) {
          return jsonResponse(request, { error: "Missing instrument token" }, 400);
        }

        const now = new Date();
        // Pull last 4 days so weekends / pre-open still return recent genuine NSE candles!
        const fromDate = new Date(now.getTime() - 4 * 24 * 3600 * 1000);
        const histUrl = `https://api.kite.trade/instruments/historical/${encodeURIComponent(token)}/${encodeURIComponent(interval)}?from=${encodeURIComponent(formatISTDate(fromDate))}&to=${encodeURIComponent(formatISTDate(now))}`;

        const resp = await fetch(histUrl, {
          headers: {
            "X-Kite-Version": "3",
            "Authorization": `token ${apiKey}:${accessToken}`
          }
        });
        const json = await resp.json();
        if (!resp.ok || json.status !== "success") {
          return jsonResponse(request, { error: json.message || "Historical fetch failed" }, resp.status || 502);
        }

        const raw = (json.data && json.data.candles) ? json.data.candles : [];
        const sliced = raw.slice(-450);
        const candles = sliced.map((row, idx) => ({
          barIndex: idx,
          time: new Date(row[0]).getTime(),
          open: row[1],
          high: row[2],
          low: row[3],
          close: row[4],
          volume: row[5] || 0
        }));

        return jsonResponse(request, { status: "success", count: candles.length, candles });
      } catch (err) {
        return jsonResponse(request, { error: String(err) }, 500);
      }
    }

    return jsonResponse(request, { error: "Not found. Read-only endpoints: /health, /api/session, /api/quotes, /api/historical" }, 404);
  }
};
