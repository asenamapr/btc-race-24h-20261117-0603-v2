[![make.fun · btc-race-24h-20261117-0603](https://make.fun/badge/btc-race-24h-20261117-0603.svg)](https://make.fun/bounty/btc-race-24h-20261117-0603?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261117-0603)
[![rank](https://make.fun/badge/btc-race-24h-20261117-0603/asenamapr/btc-race-24h-20261117-0603-v2/rank.svg)](https://make.fun/bounty/btc-race-24h-20261117-0603/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261117-0603)
[![reward](https://make.fun/badge/btc-race-24h-20261117-0603/asenamapr/btc-race-24h-20261117-0603-v2/reward.svg)](https://make.fun/bounty/btc-race-24h-20261117-0603?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261117-0603)

# BTC Dual-Regime Bot — make.fun `btc-race-24h-20261117-0603`

Entry for the [make.fun bounty](https://make.fun/bounty/btc-race-24h-20261117-0603): Race a BTC trading bot live for 24 hours.

A bot that trades cbBTC (CBBTC) against USDC on 1-minute bars with $1,000 of
paper money, for the make.fun competition "Race a BTC trading bot live for
24 hours". Python 3.13, standard library only.

## Strategy — dual regime

1-minute BTC noise (~6 bps/min) is far below the ~26 bps round-trip cost
(4 bps fee + 2 bps slippage + constant-product impact), so 1-minute signals
lose. This bot switches legs by regime, measured by the EMA30/EMA60 spread:

- **RANGE regime (spread ≤ 30 bps) — dip leg:** buy a dip against the
  **120-minute (2h) SMA** anchor: close ≥ 60 bps below the anchor, with the
  close above the 15-min SMA (short-term bounce), the dip shallowing
  (z-score rising vs 15 bars ago), and the 60-min SMA no more than 100 bps
  below the anchor (no falling knife). Sell when the close recovers to
  +50 bps above the anchor, or at +150 bps over the fill, or at −100 bps
  under it. At most 1 dip trip per window.
- **TREND regime (spread > 30 bps) — breakout leg:** buy a Donchian
  breakout — the fast EMA crossed above the slow EMA within the last 60
  bars, the spread is above 30 bps, the close is above the fast EMA and
  above the highest high of the previous 60 bars. Sell on a two-stage
  trailing stop (80 bps below the peak, tightening to 50 bps once the peak
  gain reaches 100 bps), or at +400 bps over the fill. At most 2 trend
  trips per window.
- **Discipline:** at most 3 round trips per window in total, and a 120-bar
  cooldown after a losing exit. No trading until 241 closes have been seen.

## Backtest (offline replay harness, official fill model)

| Window | Net PnL | Round trips | Max DD |
| --- | --- | --- | --- |
| dev (frozen 1,440 bars) | **+$3.87** | 1 | 0.66% |
| OOS d0 | +$4.63 | 1 | 0.67% |
| OOS d1 | +$0.02 | 1 | 0.97% |
| OOS d2 | −$3.94 | 2 | 1.42% |
| OOS d3 | +$9.13 | 1 | 0.78% |
| OOS d5 | −$5.26 | 1 | 1.10% |
| OOS d7 | $0.00 | 0 | 0.00% |
| OOS d10 | $0.00 | 0 | 0.00% |
| OOS d14 | $0.00 | 0 | 0.00% |

- OOS mean (8 windows): **+$0.57**; all-9 mean: +$0.94.
- Beats buy-and-hold in **6 of 9** windows; worst window −$5.26.
- Buy-and-hold on the same windows: dev +$1.07, d0 −$7.63, d1 +$8.62,
  d2 −$48.57, d3 −$25.84, d5 −$8.87, d7 +$5.87, d10 +$4.48, d14 −$18.61.
- Deterministic: byte-identical action logs across replays.

See `BACKTEST.md` for the full numbers, parameters, and how this differs
from v1 (the "SMA240 Dip Buyer").
