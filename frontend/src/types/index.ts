export interface BotStatus {
  running: boolean;
  symbol: string;
  long_symbol: string;
  short_symbol: string;
  bias: 'long' | 'short' | 'both' | 'off';
  dry_run: boolean;
  testnet: boolean;
  bot_name?: string;
  account_name?: string;
  equity?: number;
  emergency_stop: {
    stopped: boolean;
    reason?: string;
    stop_time?: string;
  };
  active_position_sets: number;
  max_position_sets: number;
  cooldown_remaining: number;
  latest_candle_time?: string;
  current_price?: number;
  daily_open_price?: number;
  long_daily_open_price?: number;
  short_daily_open_price?: number;
  current_drawdown_pct?: number;
  current_long_move_pct?: number;
  current_short_move_pct?: number;
  long_entry_levels_pct: number[];
  short_entry_levels_pct: number[];
  filled_levels_today: number[];
  filled_levels_today_short: number[];
  target_profit_pct: number;
  hedge_enabled: boolean;
  close_hedge_with_future: boolean;
  total_pnl: number;
  total_exposure: {
    perp_qty: number;
    option_contracts: number;
  };
}

export interface Leg {
  leg_type: 'perp' | 'option';
  symbol: string;
  side: 'short' | 'long';
  qty: number;
  entry_price?: number;
  exit_price?: number;
  mark_price?: number;
  unrealized_pnl: number;
  filled: boolean;
  filled_qty: number;
  closed: boolean;
  strike?: number;
  expiry?: string;
  option_type?: 'Call' | 'Put';
}

export interface PositionSet {
  set_id: string;
  bias: 'short' | 'long';
  state: 'opening' | 'open' | 'closing' | 'closed' | 'error' | 'partial' | 'hedge_only';
  created_at: string;
  opened_at?: string;
  closed_at?: string;
  perp_leg?: Leg;
  option_leg?: Leg;
  combined_pnl: number;
  high_water_mark: number;
  target_profit_pct: number;
  target_exit_price?: number | null;
  max_loss_usd?: number | null;
  hold_time_minutes?: number;
  entry_signal_price?: number;
  daily_open_price?: number;
  trading_day?: string;
  ladder_level?: number;
  trigger_pct?: number;
  close_hedge_with_future: boolean;
  error_message?: string;
}

export interface HedgeConfig {
  enabled: boolean;
  hedge_otm_pct: number;
  hedge_dte_min_days: number;
  close_with_future: boolean;
  slippage_bps: number;
}

export interface BotConfig {
  bot_name: string;
  account_name: string;
  long_symbol: string;
  short_symbol: string;
  bias: 'long' | 'short' | 'both' | 'off';
  timeframe: '5m';
  long_entry_levels_pct: number[];
  short_entry_levels_pct: number[];
  target_profit_pct: number;
  max_loss_usd?: number | null;
  max_position_sets: number;
  cooldown_minutes: number;
  perp_qty: number;
  hedge_config: HedgeConfig;
  poll_interval_seconds: number;
  use_testnet: boolean;
  dry_run: boolean;
  log_level: 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR';
}

export interface WSMessage {
  type: string;
  timestamp: string;
  data: any;
}

export interface EquityPoint {
  timestamp: string;
  equity: number;
}

export interface EquityHistoryResponse {
  points: EquityPoint[];
  count: number;
  available: boolean;
  dry_run: boolean;
}
