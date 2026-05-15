import React from 'react';
import { BotConfig, BotStatus } from '../types';
import { useAPI } from '../hooks/useBot';
import PriceChart from './PriceChart';

interface OverviewProps {
  status: BotStatus | null;
}

interface ChartData {
  candles: Array<{
    timestamp: number;
    close: number;
    datetime: string;
  }>;
  reference_values: number[];
  reference_label: string;
}

export default function Overview({ status }: OverviewProps) {
  const api = useAPI();
  const [loading, setLoading] = React.useState(false);
  const [chartData, setChartData] = React.useState<ChartData | null>(null);
  const [chartLoading, setChartLoading] = React.useState(true);
  const [config, setConfig] = React.useState<BotConfig | null>(null);

  React.useEffect(() => {
    const fetchChartData = async () => {
      try {
        const response = await fetch('/api/chart-data?limit=50');
        if (response.ok) {
          setChartData(await response.json());
        }
      } catch (err) {
        console.error('Failed to fetch chart data:', err);
      } finally {
        setChartLoading(false);
      }
    };

    fetchChartData();
    const interval = setInterval(fetchChartData, 30000);
    return () => clearInterval(interval);
  }, []);

  React.useEffect(() => {
    const loadConfig = async () => {
      try {
        setConfig(await api.getConfig());
      } catch (err) {
        console.error('Failed to load overview config:', err);
      }
    };
    loadConfig();
  }, []);

  const handleStart = async () => {
    setLoading(true);
    try {
      await api.startBot();
    } catch (err) {
      console.error('Failed to start bot:', err);
      alert('Failed to start bot');
    } finally {
      setLoading(false);
    }
  };

  const handleStop = async () => {
    setLoading(true);
    try {
      await api.stopBot();
    } catch (err) {
      console.error('Failed to stop bot:', err);
      alert('Failed to stop bot');
    } finally {
      setLoading(false);
    }
  };

  const handleEmergencyStop = async () => {
    if (!confirm('Emergency stop will close all tracked legs. Continue?')) return;
    setLoading(true);
    try {
      await api.emergencyStop();
    } catch (err) {
      console.error('Emergency stop failed:', err);
      alert('Emergency stop failed');
    } finally {
      setLoading(false);
    }
  };

  if (!status) {
    return <div className="card">Loading...</div>;
  }

  const futuresSymbol = status.symbol?.replace('USDT', '').replace('USDC', '') ?? 'coin';
  const filledLevels = status.filled_levels_today
    .map((index) => status.entry_levels_pct[index])
    .filter((value) => value !== undefined);

  return (
    <div>
      <div className="card">
        <h2 className="card-title">
          {status.bot_name ? `${status.bot_name} - Bot Controls` : 'Bot Controls'}
        </h2>
        <div className="button-group">
          {!status.running ? (
            <button className="button success" onClick={handleStart} disabled={loading}>
              Start Bot
            </button>
          ) : (
            <button className="button danger" onClick={handleStop} disabled={loading}>
              Stop Bot
            </button>
          )}
          <button className="button danger" onClick={handleEmergencyStop} disabled={loading}>
            Emergency Stop
          </button>
        </div>
      </div>

      <div className="card">
        <h2 className="card-title">Portfolio</h2>
        <div className="stats-grid">
          {status.equity !== undefined && !status.dry_run && (
            <div className="stat-card">
              <div className="stat-label">Account Equity</div>
              <div className="stat-value">${status.equity.toFixed(2)}</div>
            </div>
          )}
          <div className="stat-card">
            <div className="stat-label">Active Position Sets</div>
            <div className="stat-value">
              {status.active_position_sets} / {status.max_position_sets}
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Total PnL</div>
            <div className={`stat-value ${status.total_pnl >= 0 ? 'positive' : 'negative'}`}>
              ${status.total_pnl.toFixed(2)}
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Perp Exposure</div>
            <div className="stat-value">{status.total_exposure.perp_qty.toFixed(3)} {futuresSymbol}</div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Put Contracts</div>
            <div className="stat-value">{status.total_exposure.option_contracts.toFixed(3)}</div>
          </div>
        </div>
      </div>

      <div className="card">
        <h2 className="card-title">Strategy Summary</h2>
        <div className="strategy-note-grid">
          <div className="strategy-note-block">
            <div className="strategy-note-label">Reference</div>
            <div className="strategy-note-text">
              UTC 00:00 daily open on {status.symbol}
            </div>
          </div>
          <div className="strategy-note-block">
            <div className="strategy-note-label">Ladder</div>
            <div className="strategy-note-text">
              {config ? config.entry_levels_pct.join('%, ') : status.entry_levels_pct.join('%, ')}%
            </div>
          </div>
          <div className="strategy-note-block">
            <div className="strategy-note-label">Take Profit</div>
            <div className="strategy-note-text">
              Exit each futures leg at +{config?.target_profit_pct ?? status.target_profit_pct}%
            </div>
          </div>
          <div className="strategy-note-block">
            <div className="strategy-note-label">Hedge</div>
            <div className="strategy-note-text">
              {config?.hedge_config.enabled
                ? `Long put, min ${config.hedge_config.hedge_otm_pct}% OTM, min ${config.hedge_config.hedge_dte_min_days} DTE, ${config.hedge_config.close_with_future ? 'close with futures' : 'leave open after futures exit'}`
                : 'Hedge disabled'}
            </div>
          </div>
          <div className="strategy-note-block">
            <div className="strategy-note-label">Filled Today</div>
            <div className="strategy-note-text">
              {filledLevels.length > 0 ? `${filledLevels.join('%, ')}%` : 'No ladder levels filled yet'}
            </div>
          </div>
          <div className="strategy-note-block">
            <div className="strategy-note-label">Execution Mode</div>
            <div className="strategy-note-text">
              {status.dry_run ? 'Dry run' : 'Live'} on {status.testnet ? 'testnet' : 'mainnet'}
            </div>
          </div>
        </div>
      </div>

      <div className="card">
        <h2 className="card-title">Status</h2>
        <div className="stats-grid">
          <div className="stat-card">
            <div className="stat-label">Bot Status</div>
            <div className="stat-value">
              <span className={`badge ${status.running ? 'success' : 'error'}`}>
                {status.running ? 'Running' : 'Stopped'}
              </span>
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Daily Open</div>
            <div className="stat-value">
              {status.daily_open_price ? `$${status.daily_open_price.toFixed(2)}` : 'N/A'}
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Current Drawdown</div>
            <div className="stat-value">
              {status.current_drawdown_pct !== undefined && status.current_drawdown_pct !== null
                ? `${status.current_drawdown_pct.toFixed(2)}%`
                : 'N/A'}
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Cooldown</div>
            <div className="stat-value">
              {status.cooldown_remaining > 0 ? `${status.cooldown_remaining.toFixed(1)} min` : 'Ready'}
            </div>
          </div>
        </div>
      </div>

      <PriceChart data={chartData} loading={chartLoading} />

      <div className="card">
        <h2 className="card-title">Market Data</h2>
        <div className="stats-grid">
          <div className="stat-card">
            <div className="stat-label">Current Price</div>
            <div className="stat-value">
              {status.current_price ? `$${status.current_price.toFixed(2)}` : 'N/A'}
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Entry Thresholds</div>
            <div className="stat-value">{status.entry_levels_pct.join('%, ')}%</div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Last Candle</div>
            <div className="stat-value text-muted">
              {status.latest_candle_time ? new Date(status.latest_candle_time).toLocaleTimeString() : 'N/A'}
            </div>
          </div>
        </div>
      </div>

      {status.emergency_stop.stopped && (
        <div className="card" style={{ borderColor: 'var(--accent-error)' }}>
          <h2 className="card-title text-error">Emergency Stop Active</h2>
          <p className="text-muted">Reason: {status.emergency_stop.reason}</p>
          {status.emergency_stop.stop_time && (
            <p className="text-muted">
              Time: {new Date(status.emergency_stop.stop_time).toLocaleString()}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
