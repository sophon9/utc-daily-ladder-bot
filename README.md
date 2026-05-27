# Advantage Price Bot for Bybit

This app monitors the current UTC trading day open and opens a new long futures position when price drops by configured ladder percentages such as `x`, `y`, and `z`.

The current code supports `long`, `short`, `both`, and `off` bias modes with separate ladder arrays for long and short entries.

## Core Config

`long_entry_levels_pct`
- Drawdown percentages from the UTC `00:00` daily open that trigger long entries.

`short_entry_levels_pct`
- Rally percentages from the UTC `00:00` daily open that trigger short entries.

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
