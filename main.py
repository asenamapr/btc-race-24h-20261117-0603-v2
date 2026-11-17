"""BTC dual-regime bot for make.fun btc-race-24h-20261117-0603.

Strategy (long only, one position, full size) — DUAL REGIME. Genuinely
different from v1 ("SMA240 Dip Buyer", a single-regime mean-reversion dip
buyer): this bot switches legs by regime, and neither leg is v1's.

Regime: the EMA30/EMA60 spread. Spread above 30 bps = TREND regime,
spread at or below 30 bps = RANGE regime.

* DIP leg (RANGE regime only): buy a dip against the SMA_DIP anchor
  (2h, not v1's 4h): close at least DIP_ENTRY bps below the anchor, with
  the close above the 15-min SMA (short-term bounce), the dip shallowing
  (z-score rising vs 15 bars ago), and the 60-min SMA no more than 100
  bps below the anchor (no falling knife). Sell when the close recovers
  to DIP_EXIT bps above the anchor, or at DIP_TP over the fill, or at
  DIP_SL under it. At most 1 dip trip per window.
* TREND leg (TREND regime only): buy a breakout — the fast EMA crossed
  above the slow EMA within the last 60 bars, the spread is above 30
  bps, the close is above the fast EMA and above the highest high of
  the previous 60 bars. Sell on a two-stage trailing stop (80 bps below
  the peak, tightening to 50 bps once the peak gain reaches 100 bps),
  or at +400 bps over the fill. At most 2 trend trips per window.
* Discipline: at most 3 round trips per window in total, and a 120-bar
  cooldown after a losing exit.

Cold start: no trading until WARMUP_CLOSES closes have been seen. All
decisions are deterministic: plain float arithmetic over the bars as they
arrive, no clock, no randomness, no network, no files.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

SYMBOL = "CBBTC"
MAX_SLIPPAGE_BPS = 100

# --- dip leg parameters ---
DIP_SMA_BARS = 120        # dip anchor length (2h)
DIP_ENTRY_BPS = 60        # buy when close is this far below the dip anchor
DIP_EXIT_BPS = 50         # sell when close recovers this far above the anchor
DIP_TP_BPS = 150          # dip-leg take profit over the fill price
DIP_SL_BPS = 100          # dip-leg stop loss under the fill price
DIP_MAX_TRIPS = 1
# --- trend leg parameters ---
EMA_FAST_BARS = 30
EMA_SLOW_BARS = 60
TREND_SPREAD_BPS = 30     # spread above this = TREND regime
CROSS_WINDOW_BARS = 60
DONCHIAN_BARS = 60
TRAIL1_BPS = 80
TRAIL2_BPS = 50
STAGE_BPS = 100
TREND_TP_BPS = 400
TREND_MAX_TRIPS = 2
# --- shared discipline ---
MAX_ROUND_TRIPS = 3
STOP_COOLDOWN_BARS = 120
MID_BARS = 60             # no-falling-knife filter SMA length
FAST_BARS = 15            # short-term bounce SMA length
TREND_TOL_BPS = 100       # mid SMA may sit at most this far below the dip anchor
MAX_HOLD_BARS = 1440
WARMUP_CLOSES = 241


class Series:
    """Rolling EMAs/SMAs, z-history, and Donchian highs."""

    def __init__(self):
        self.closes = []
        self.highs = []
        self.ema_fast = None
        self.ema_slow = None
        self._a_fast = 2.0 / (EMA_FAST_BARS + 1)
        self._a_slow = 2.0 / (EMA_SLOW_BARS + 1)
        self.last_cross = -10**9
        self._sum_dip = 0.0
        self._sum_mid = 0.0
        self._sum_fast = 0.0
        self.dip_hist = []

    def push(self, close, high):
        c = float(close)
        self.closes.append(c)
        self.highs.append(float(high))
        n = len(self.closes)
        # EMAs (trend leg).
        prev_fast = self.ema_fast
        prev_slow = self.ema_slow
        if self.ema_fast is None:
            self.ema_fast = c
            self.ema_slow = c
        else:
            self.ema_fast = self._a_fast * c + (1.0 - self._a_fast) * self.ema_fast
            self.ema_slow = self._a_slow * c + (1.0 - self._a_slow) * self.ema_slow
        if prev_fast is not None and prev_fast <= prev_slow and self.ema_fast > self.ema_slow:
            self.last_cross = n - 1
        # SMAs (dip leg).
        self._sum_dip += c
        self._sum_mid += c
        self._sum_fast += c
        if n > DIP_SMA_BARS:
            self._sum_dip -= self.closes[n - 1 - DIP_SMA_BARS]
        if n > MID_BARS:
            self._sum_mid -= self.closes[n - 1 - MID_BARS]
        if n > FAST_BARS:
            self._sum_fast -= self.closes[n - 1 - FAST_BARS]
        self.dip_hist.append(self._sum_dip / DIP_SMA_BARS if n >= DIP_SMA_BARS else 0.0)

    @property
    def dip(self):
        return self._sum_dip / DIP_SMA_BARS

    @property
    def mid(self):
        return self._sum_mid / MID_BARS

    @property
    def fast(self):
        return self._sum_fast / FAST_BARS

    def z_now(self):
        return (self.closes[-1] - self.dip) / self.dip

    def z_15_ago(self):
        i = len(self.closes) - 1 - FAST_BARS
        s = self.dip_hist[i]
        if s == 0.0:
            return self.z_now()
        return (self.closes[i] - s) / s

    def donchian_high(self):
        n = DONCHIAN_BARS
        if n <= 0 or len(self.highs) <= n:
            return None
        return max(self.highs[-n - 1:-1])


# --- run state (module level; one run per process) ---
series = Series()
entry_price = None
entry_seq = -1
peak = None
leg = None              # "dip" | "trend" for the open position
round_trips = 0
dip_trips = 0
trend_trips = 0
cool_until_seq = -1
pending_buy = False
pending_sell = False
my_orders = {}


def on_batch(state, batch):
    global entry_price, entry_seq, peak, leg, round_trips, dip_trips, trend_trips
    global cool_until_seq, pending_buy, pending_sell

    for fill in batch.get("fills", []):
        side = my_orders.get(fill.get("client_id"))
        if side is None:
            continue
        if fill.get("status") == "filled":
            if side == "buy":
                entry_price = int(fill["price"])
                entry_seq = state.seq
                peak = entry_price
                pending_buy = False
            else:
                if leg == "dip":
                    dip_trips += 1
                elif leg == "trend":
                    trend_trips += 1
                if entry_price is not None and int(fill["price"]) < entry_price:
                    # A losing exit: cool down before re-entering.
                    cool_until_seq = state.seq + STOP_COOLDOWN_BARS
                round_trips += 1
                entry_price = None
                peak = None
                leg = None
                pending_sell = False
        else:
            if side == "buy":
                pending_buy = False
            else:
                pending_sell = False

    bar = None
    for b in batch.get("bars", []):
        if b.get("symbol") == SYMBOL:
            bar = b
            break
    if bar is None or state.warming_up:
        return []
    series.push(int(bar["c"]), int(bar["h"]))
    if len(series.closes) < WARMUP_CLOSES:
        return []

    held = state.positions.get(SYMBOL)
    close = series.closes[-1]

    if held is None:
        if pending_buy or round_trips >= MAX_ROUND_TRIPS or state.seq < cool_until_seq:
            return []
        spread_bps = (series.ema_fast / series.ema_slow - 1.0) * 10000.0
        want = None
        if spread_bps > TREND_SPREAD_BPS:
            # TREND leg: fresh cross + close above fast EMA + Donchian breakout.
            dh = series.donchian_high()
            cross_age = len(series.closes) - 1 - series.last_cross
            if (
                trend_trips < TREND_MAX_TRIPS
                and cross_age <= CROSS_WINDOW_BARS
                and close > series.ema_fast
                and (dh is None or close > dh)
            ):
                want = "trend"
        else:
            # DIP leg: deep dip + bounce + shallowing + no falling knife.
            z = series.z_now()
            if (
                dip_trips < DIP_MAX_TRIPS
                and z <= -DIP_ENTRY_BPS / 10000.0
                and close > series.fast
                and z > series.z_15_ago()
                and series.mid >= series.dip * (1 - TREND_TOL_BPS / 10000.0)
            ):
                want = "dip"
        if want is not None:
            notional = state.cash
            if notional < int(state.hello["fees"]["min_notional_quote_units"]):
                return []
            pending_buy = True
            leg = want
            cid = state.client_id()
            my_orders[cid] = "buy"
            return [{
                "side": "buy",
                "client_id": cid,
                "symbol": SYMBOL,
                "notional_quote_units": notional,
                "max_slippage_bps": MAX_SLIPPAGE_BPS,
            }]
        return []

    # --- holding: exit by the leg that opened the position ---
    if pending_sell:
        return []
    if peak is None:
        peak = entry_price
    if close > peak:
        peak = close
    ret = close / entry_price - 1.0 if entry_price else 0.0
    hold_bars = state.seq - entry_seq
    do_sell = False
    if leg == "dip":
        z = series.z_now()
        stop_hit = ret <= -DIP_SL_BPS / 10000.0
        do_sell = (
            z >= DIP_EXIT_BPS / 10000.0
            or ret >= DIP_TP_BPS / 10000.0
            or stop_hit
            or hold_bars >= MAX_HOLD_BARS
        )
    else:  # trend leg: two-stage trailing stop
        gain_bps = (peak / entry_price - 1.0) * 10000.0 if entry_price else 0.0
        trail = TRAIL2_BPS if gain_bps >= STAGE_BPS else TRAIL1_BPS
        do_sell = (
            close <= peak * (1 - trail / 10000.0)
            or ret >= TREND_TP_BPS / 10000.0
            or hold_bars >= MAX_HOLD_BARS
        )
    if do_sell:
        pending_sell = True
        cid = state.client_id()
        my_orders[cid] = "sell"
        return [{
            "side": "sell",
            "client_id": cid,
            "symbol": SYMBOL,
            "qty": held.qty,
            "max_slippage_bps": MAX_SLIPPAGE_BPS,
        }]
    return []


makefun_bars.run(on_batch)
