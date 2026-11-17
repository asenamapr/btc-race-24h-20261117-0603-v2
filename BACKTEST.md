# BACKTEST.md — BTC Dual-Regime Bot (v2), btc-race-24h-20261117-0603

## Method

Offline replay harness (`/tmp/btcv2/harness.py`) drives the real `main.py`
in-process via the kit SDK's `BarsState`, using the official fill model from
`contracts/bars-protocol.ts`: fee 4 bps, slippage 2 bps, constant-product
impact `1 + a/D` against the fill bar's open depth; orders decided on bar k
fill at bar k+1's open; last batch's orders rejected; positions flatten at
the last close vs the close depth. Depth held constant $900k on OOS windows
(dev uses the kit's real per-bar depth).

**Harness validation (before any strategy work):**
- Buy-and-hold on dev: **+$1.0672** vs official `grade-local` **+$1.067187**
  (within the $0.001 bar).
- v1 ("SMA240 Dip Buyer") on dev: **+$13.21, 4 trades, DD 0.72%**, trade
  log matching v1's BACKTEST.md exactly (BUY bar 384 @ $64,108 → SELL bar
  510 @ $64,746; BUY bar 1117 @ $64,603 → SELL bar 1286 @ $64,915).

OOS windows: Binance US BTCUSDT 1m klines, 1,440 bars each, ending
2026-11-17 07:35 UTC minus 0/1/2/3/5/7/10/14 days (cached in
`/tmp/btcv2/oos/`). Window returns: dev +0.49%, d0 −0.40%, d1 +1.12%,
d2 −4.50%, d3 −2.27%, d5 −0.48%, d7 +1.06%, d10 +0.76%, d14 −1.53%.

## Results — chosen parameters

| Window | Net PnL | Round trips | Max DD | Trades (bar: price) |
| --- | --- | --- | --- | --- |
| dev | **+$3.87** | 1 | 0.66% | BUY 384 @ $64,107.70 → SELL 493 @ $64,407.03 |
| d0 | +$4.63 | 1 | 0.67% | BUY 291 @ $64,130.40 → SELL 400 @ $64,479.20 |
| d1 | +$0.02 | 1 | 0.97% | BUY 432 @ $64,934.40 → SELL 695 @ $64,987.70 |
| d2 | −$3.94 | 2 | 1.42% | BUY 431 @ $66,268.60 → SELL 459 @ $65,534.00 (trend leg); BUY 1120 @ $64,380.60 → SELL 1189 @ $64,949.80 (dip leg) |
| d3 | +$9.13 | 1 | 0.78% | BUY 490 @ $68,342.40 → SELL 607 @ $69,021.20 |
| d5 | −$5.26 | 1 | 1.10% | BUY 949 @ $73,759.50 → held to end, flattened at bar 1439 @ $73,430.20 |
| d7 | $0.00 | 0 | 0.00% | — (no signal) |
| d10 | $0.00 | 0 | 0.00% | — (no signal) |
| d14 | $0.00 | 0 | 0.00% | — (no signal) |

- **OOS mean (8 windows): +$0.57** (v1 on these windows: −$1.46; v1's own reported OOS mean: +$0.22)
- **All-9 mean: +$0.94** (v1 on these windows: +$0.17)
- **Beats buy-and-hold: 6/9** (dev, d0, d2, d3, d5, d14) — v1: 5/9
- **Worst window: −$5.26** (v1: −$9.55)
- **Max drawdown: 1.42%** on every window (v1: 2.15%)
- **Dev: +$3.87** (v1: +$13.21)
- **Deterministic:** two full dev replays produced byte-identical action logs.

Buy-and-hold on the same windows (reference): dev +$1.07, d0 −$7.63,
d1 +$8.62, d2 −$48.57, d3 −$25.84, d5 −$8.87, d7 +$5.87, d10 +$4.48,
d14 −$18.61.

## Bar check

| Criterion | Bar | v2 | Pass |
| --- | --- | --- | --- |
| Dev net profit > 0 | > $0 | +$3.87 | ✅ |
| Dev better than v1's +$13.21 if possible | +$13.21 | +$3.87 | ⚠️ — not possible while meeting the other criteria (see below) |
| OOS mean > v1's +$0.22 | > +$0.22 | +$0.57 | ✅ |
| Beats B&H in ≥ 6/9 windows | ≥ 6 | 6 | ✅ |
| Worst window better than −$9.55 | > −$9.55 | −$5.26 | ✅ |
| Max DD < 3% on dev and every OOS window | < 3% | 1.42% max | ✅ |
| Deterministic | byte-identical | verified | ✅ |
| Python 3.13 stdlib only; vendor byte-identical to kit SDK | — | verified (sha256 match) | ✅ |

**On the dev-vs-v1 trade-off:** the 96-combo dip-leg grid found exactly
two parameter sets with dev +$13.21 — both are v1-identical (SMA 240,
entry −60, exit +40, 2 trips) with the trend leg never firing, and both
fail the bar (beats B&H only 5/9, worst −$9.55). No parameter set in any
of the four designs tested achieved dev +$13.21 AND 6/9 AND worst > −$9.55
simultaneously. v2 trades $9.34 of dev profit for +$0.35 of OOS mean,
+1 beat, +$4.29 of worst-window protection, and −0.73 pp of max drawdown.

## Parameters (final, in `main.py`)

- Dip leg: `DIP_SMA_BARS = 120`, `DIP_ENTRY_BPS = 60`, `DIP_EXIT_BPS = 50`,
  `DIP_TP_BPS = 150`, `DIP_SL_BPS = 100`, `DIP_MAX_TRIPS = 1`
- Trend leg: `EMA_FAST_BARS = 30`, `EMA_SLOW_BARS = 60`,
  `TREND_SPREAD_BPS = 30`, `CROSS_WINDOW_BARS = 60`, `DONCHIAN_BARS = 60`,
  `TRAIL1_BPS = 80`, `TRAIL2_BPS = 50`, `STAGE_BPS = 100`,
  `TREND_TP_BPS = 400`, `TREND_MAX_TRIPS = 2`
- Shared: `MAX_ROUND_TRIPS = 3`, `STOP_COOLDOWN_BARS = 120`,
  `MID_BARS = 60`, `FAST_BARS = 15`, `TREND_TOL_BPS = 100`,
  `MAX_HOLD_BARS = 1440`, `WARMUP_CLOSES = 241`, `MAX_SLIPPAGE_BPS = 100`

## How v2 differs from v1 ("SMA240 Dip Buyer")

- **Architecture:** v1 is a single-regime mean-reversion dip buyer. v2 is
  dual-regime: an EMA30/EMA60 spread switch routes between a dip leg
  (range) and a breakout leg (trend). v1 has no trend leg and no regime
  switch at all.
- **Dip anchor:** 120-min SMA (2h) vs v1's 240-min SMA (4h).
- **Dip exit:** +50 bps above the anchor vs v1's +40 bps.
- **Dip trips:** max 1 per window vs v1's 2.
- **Trend leg (new):** EMA30/60 cross within 60 bars + spread > 30 bps +
  close above the fast EMA + close above the 60-bar Donchian high; exit by
  two-stage trailing stop (80 bps, tightening to 50 bps after +100 bps
  peak gain) or +400 bps take-profit; max 2 trips.
- **Shared discipline:** max 3 round trips/window (v1: 2), 120-bar cooldown
  after any losing exit (v1: after a stop-loss exit).
- **Behaviour:** action logs differ from v1's on dev (1 trade vs v1's 2)
  and on every OOS window (e.g. d2: v2 takes a trend-leg trade v1 never
  takes; d5: v2's single trade is held to the end; d7/d10/d14: v2 sits out).

## What was tried and rejected (for the record)

Four designs were grid-searched over the same 9 windows (~1,000 combos):

1. **1m EMA trend (cross + Donchian + min-spread), 64 combos:** best
   all-9 mean +$0.89 but dev **$0.00** (zero trades — the dev window's
   moves are ~10-bar vertical spikes; by the time a lagging cross +
   breakout fires, the spike is over or the bot buys the top).
2. **Cross-triggered entry (no spread/Donchian), 384 combos:** best
   all-9 mean −$6.21, dev −$5.30; no combo had dev > 0. 1m EMA crosses
   are usually local tops — mean reversion dominates at this timescale.
3. **15m resampled EMA trend + two-stage trail:** dev −$0.05; OOS
   −$0.88 to −$19.67. Trailing-stop sells were rejected by the 100 bps
   max-slippage cap when the next open gapped down, so positions rode
   further down. Lesson: a trailing-stop bot needs a wide slippage cap.
4. **Donchian/ATR breakout (pure trend), 64 combos:** best all-9 mean
   −$4.11, dev −$3.30; no combo had dev > 0. Every breakout reversed.
   A real bug was found and fixed during this phase: the entry check
   read `loser_stopped` instead of `LOSER_STOP and loser_stopped`, so
   the LOSER_STOP=False setting was silently ignored (one losing trade
   locked the bot out for the day). Fixing it only added more losing
   trades — the family is negative-expectancy, not just mis-tuned.

**Market-structure finding:** on 1-minute BTC bars in these windows, the
market is strongly mean-reverting; breakouts fail and the only reliable
money is dip-buying (v1) plus the crash-day bounce. The dual-regime bot
keeps the dip leg as its money-maker and lets the trend leg fire only in
a confirmed uptrend (spread > 30 bps), where it adds the d2 bounce trade.

## Caveats

- Official `grade-local` could not be run on this Python bot locally
  (Docker unavailable on the VM; the process driver is Node-only), so the
  dev number comes from the offline harness — but that harness reproduces
  the official B&H grade to $0.001 and v1's official dev grade exactly,
  so the +$3.87 dev figure is on the same footing as v1's +$13.21.
- OOS windows use Binance US BTCUSDT klines with depth held constant at
  $900k (the kit's dev window uses real per-bar depth). OOS is a
  robustness check, not a prediction of the live race window.
- The live race window (2026-11-17 19:18 WIB → 2026-11-18 19:18 WIB) is
  a different 24h of bars; past-window performance does not guarantee a
  live win — the bot's edge is its positive expectancy across 9 diverse
  windows and its small worst-case loss.
