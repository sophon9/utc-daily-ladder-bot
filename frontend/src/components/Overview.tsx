import React from 'react';
import { BotConfig, BotStatus, EquityHistoryResponse } from '../types';
import { useAPI } from '../hooks/useBot';
import EquityCurve from './EquityCurve';
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

function LadderPill({
  level,
  filled,
  currentDrawdownPct,
}: {
  level: number;
  filled: boolean;
  currentDrawdownPct?: number;
}) {
  const armed = currentDrawdownPct !== undefined && currentDrawdownPct >= level;
  return (
    <div className={`ladder-pill ${filled ? 'filled' : armed ? 'armed' : ''}`}>
      <span>{level.toFixed(1)}%</span>
      <strong>{filled ? 'Filled' : armed ? 'Armed' : 'Waiting'}</strong>
    </div>
  );
}

export default function Overview({ status }: OverviewProps) {
  const api = useAPI();
  const [loading, setLoading] = React.useState(false);
  const [chartData, setChartData] = React.useState<ChartData | null>(null);
  const [chartLoading, setChartLoading] = React.useState(true);
  const [config, setConfig] = React.useState<BotConfig | null>(null);
  const [equityHistory, setEquityHistory] = React.useState<EquityHistoryResponse | null>(null);

  React.useEffect(() => {
    const fetchChartData = async () => {
      try {
        const response = await fetch('/api/chart-data?limit=72');
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
    const loadStaticData = async () => {
      try {
        const [cfg, history] = await Promise.all([
          api.getConfig(),
          api.getEquityHistory(240),
        ]);
        setConfig(cfg);
        setEquityHistory(history);
      } catch (err) {
        console.error('Failed to load overview data:', err);
      }
    };

    loadStaticData();
  }, [api]);

  const handleStart = async () => {
    setLoading(true);
    try {
      const result = await api.startBot();
      if (result.detail) {
        alert(result.detail);
      }
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
    return <div className="panel panel-empty">Loading live market state...</div>;
  }

  const equityPoints = equityHistory?.points ?? [];
  const filledLevels = new Set(status.filled_levels_today);
  const currentDrawdown = status.current_drawdown_pct ?? 0;
  const thresholdGap = status.entry_levels_pct.length > 0
    ? Math.min(...status.entry_levels_pct.map((level) => level - currentDrawdown).filter((value) => value > 0))
    : null;

  return (
    <div className="overview-shell">
      <section className="hero">
        <div className="hero-copy">
          <span className="hero-kicker">UTC Daily Open Ladder</span>
          <h2>{status.symbol} rebound capture with protective put hedges</h2>
          <p>
            The bot tracks drawdown from the UTC session open, scales into configured long entries,
            and pairs each futures fill with a long OTM put hedge.
          </p>
          <div className="hero-actions">
            {!status.running ? (
              <button className="button button-primary" onClick={handleStart} disabled={loading}>
                Start Monitoring
              </button>
            ) : (
              <button className="button button-danger" onClick={handleStop} disabled={loading}>
                Pause Bot
              </button>
            )}
            <button className="button button-ghost" onClick={handleEmergencyStop} disabled={loading}>
              Emergency Stop
            </button>
          </div>
        </div>

        <div className="hero-aside">
          <div className="mode-stack">
            <div className={`mode-chip ${status.running ? 'live' : 'idle'}`}>
              {status.running ? 'Monitoring active' : 'Idle'}
            </div>
            <div className={`mode-chip ${status.dry_run ? 'warn' : 'accent'}`}>
              {status.dry_run ? 'Dry run' : status.testnet ? 'Testnet' : 'Mainnet live'}
            </div>
          </div>
          <div className="hero-metric">
            <span>Current drawdown</span>
            <strong>{currentDrawdown.toFixed(2)}%</strong>
          </div>
          <div className="hero-metric">
            <span>Next trigger gap</span>
            <strong>{thresholdGap !== null ? `${thresholdGap.toFixed(2)}%` : 'All levels used'}</strong>
          </div>
          <div className="hero-metric">
            <span>Hedge posture</span>
            <strong>{status.close_hedge_with_future ? 'Auto-close with futures' : 'Leave hedge open'}</strong>
          </div>
        </div>
      </section>

      <section className="overview-grid">
        <div className="overview-column overview-column-main">
          <div className="panel">
            <div className="panel-head">
              <div>
                <h3 className="panel-title">Ladder Readiness</h3>
                <p className="panel-copy">Each rung unlocks when the live drawdown reaches the configured threshold.</p>
              </div>
            </div>
            <div className="ladder-grid">
              {status.entry_levels_pct.map((level, index) => (
                <LadderPill
                  key={`${level}-${index}`}
                  level={level}
                  filled={filledLevels.has(index)}
                  currentDrawdownPct={status.current_drawdown_pct}
                />
              ))}
            </div>
          </div>

          <PriceChart data={chartData} loading={chartLoading} />
          <EquityCurve points={equityPoints} dryRun={status.dry_run} />
        </div>

        <div className="overview-column overview-column-side">
          <div className="panel metrics-panel">
            <h3 className="panel-title">Live Snapshot</h3>
            <div className="metric-stack">
              <div className="metric-row">
                <span>Daily Open</span>
                <strong>{status.daily_open_price ? `$${status.daily_open_price.toFixed(2)}` : 'N/A'}</strong>
              </div>
              <div className="metric-row">
                <span>Current Price</span>
                <strong>{status.current_price ? `$${status.current_price.toFixed(2)}` : 'N/A'}</strong>
              </div>
              <div className="metric-row">
                <span>Take Profit</span>
                <strong>+{status.target_profit_pct.toFixed(2)}%</strong>
              </div>
              <div className="metric-row">
                <span>Active Entries</span>
                <strong>{status.active_position_sets} / {status.max_position_sets}</strong>
              </div>
              <div className="metric-row">
                <span>Perp Exposure</span>
                <strong>{status.total_exposure.perp_qty.toFixed(3)}</strong>
              </div>
              <div className="metric-row">
                <span>Put Contracts</span>
                <strong>{status.total_exposure.option_contracts.toFixed(3)}</strong>
              </div>
            </div>
          </div>

          <div className="panel">
            <h3 className="panel-title">Strategy Fit</h3>
            <div className="detail-list">
              <div>
                <span>Reference price</span>
                <strong>UTC 00:00 open</strong>
              </div>
              <div>
                <span>Entry schedule</span>
                <strong>{status.entry_levels_pct.join(' / ')}%</strong>
              </div>
              <div>
                <span>Hedge selection</span>
                <strong>
                  {config?.hedge_config.enabled
                    ? `${config.hedge_config.hedge_otm_pct}% OTM, min ${config.hedge_config.hedge_dte_min_days} DTE`
                    : 'Disabled'}
                </strong>
              </div>
              <div>
                <span>Close behavior</span>
                <strong>{status.close_hedge_with_future ? 'Close put with futures' : 'Leave put after exit'}</strong>
              </div>
              <div>
                <span>Account mode</span>
                <strong>{status.dry_run ? 'Dry run simulation' : status.testnet ? 'Testnet routing' : 'Mainnet execution'}</strong>
              </div>
            </div>
          </div>

          <div className="panel">
            <h3 className="panel-title">Performance Pulse</h3>
            <div className="detail-list">
              <div>
                <span>Total PnL</span>
                <strong className={status.total_pnl >= 0 ? 'text-success' : 'text-error'}>
                  ${status.total_pnl.toFixed(2)}
                </strong>
              </div>
              <div>
                <span>Account equity</span>
                <strong>{status.equity !== undefined ? `$${status.equity.toFixed(2)}` : status.dry_run ? 'N/A in dry run' : 'Unavailable'}</strong>
              </div>
              <div>
                <span>History points</span>
                <strong>{equityHistory?.count ?? 0}</strong>
              </div>
              <div>
                <span>Last candle</span>
                <strong>{status.latest_candle_time ? new Date(status.latest_candle_time).toLocaleTimeString() : 'N/A'}</strong>
              </div>
            </div>
          </div>
        </div>
      </section>

      {status.emergency_stop.stopped && (
        <div className="panel panel-alert">
          <h3 className="panel-title">Emergency Stop Active</h3>
          <p className="panel-copy">Reason: {status.emergency_stop.reason}</p>
        </div>
      )}
    </div>
  );
}
