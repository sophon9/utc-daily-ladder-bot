# Advantage Price Bot for Bybit

This app monitors the current UTC trading day open and opens a new long futures position when price drops by configured ladder percentages such as `x`, `y`, and `z`.

Each entry:
- opens a `long` perpetual futures position at market
- optionally opens a `long put` hedge
- selects the hedge strike as the first available put at least `hedge_otm_pct` below spot
- requires the hedge expiry to satisfy `hedge_dte_min_days`
- exits the futures leg when price reaches `target_profit_pct` above its own fill price
- optionally closes the hedge when the futures leg exits, or leaves it open as `hedge_only`

## Core Config

`entry_levels_pct`
- Drawdown percentages from the UTC `00:00` daily open that trigger entries.

`target_profit_pct`
- Take-profit percent for each futures leg, measured from that leg's own entry price.

`perp_qty`
- Futures size per ladder entry. The hedge uses the same numeric size.

`hedge_config.hedge_otm_pct`
- Minimum OTM distance for the put strike.

`hedge_config.hedge_dte_min_days`
- Minimum days to expiry for hedge options.

`hedge_config.close_with_future`
- If `true`, the hedge is closed with the futures leg.
- If `false`, the position remains tracked as `hedge_only`.

## Running

```bash
cp config.example.json config.json
./setup.sh
./run_all.sh
```

Backend runs on `8030`, frontend runs on `3030`.

Backend lives in `backend/` and frontend lives in `frontend/`.
