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
  currentMovePct,
}: {
  level: number;
  filled: boolean;
  currentMovePct?: number;
}) {
  const armed = currentMovePct !== undefined && currentMovePct >= level;
  return (
    <div className={`ladder-pill ${filled ? 'filled' : armed ? 'armed' : ''}`}>
      <span>{level.toFixed(1)}%</span>
      <strong>{filled ? 'Filled' : armed ? 'Armed' : 'Waiting'}</strong>
    </div>
  );
}

function LadderBlock({
  title,
  subtitle,
  levels,
  filledLevels,
  currentMovePct,
}: {
  title: string;
  subtitle: string;
  levels: number[];
  filledLevels: Set<number>;
  currentMovePct?: number;
}) {
  return (
    <div>
      <div style={{ marginBottom: '12px' }}>
        <div className="panel-title" style={{ fontSize: '0.95rem', marginBottom: '4px' }}>{title}</div>
        <p className="panel-copy">{subtitle}</p>
      </div>
      <div className="ladder-grid">
        {levels.map((level, index) => (
          <LadderPill
            key={`${title}-${level}-${index}`}
            level={level}
            filled={filledLevels.has(index)}
            currentMovePct={currentMovePct}
          />
        ))}
      </div>
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
  const filledLevelsLong = new Set(status.filled_levels_today);
  const filledLevelsShort = new Set(status.filled_levels_today_short ?? []);
  const isShortBias = status.bias === 'short';
  const isBothBias = status.bias === 'both';
  const currentMove = status.current_drawdown_pct ?? 0;
  const currentLongMove = status.current_long_move_pct ?? 0;
  const currentShortMove = status.current_short_move_pct ?? 0;
  const activeLevels = isShortBias ? status.short_entry_levels_pct : status.long_entry_levels_pct;
  const thresholdGap = activeLevels.length > 0
    ? Math.min(...activeLevels.map((level) => level - currentMove).filter((value) => value > 0))
    : null;
  const headline = isShortBias
    ? `${status.short_symbol} entries at advantage rally levels`
    : isBothBias
    ? `${status.long_symbol} / ${status.short_symbol} advantage price entries`
    : `${status.long_symbol} entries at advantage pullback levels`;
  const description = isShortBias
    ? 'The bot waits for price to move above the UTC daily open, then enters short positions only at configured advantage levels.'
    : isBothBias
    ? 'The bot monitors both sides of the UTC daily open and waits for configured advantage prices before entering.'
    : 'The bot waits for price to pull back below the UTC daily open, then enters long positions only at configured advantage levels.';
  const moveLabel = isShortBias ? 'Move from open' : isBothBias ? 'Largest move from open' : 'Move from open';
  const strategyPanelCopy = isShortBias
    ? 'Each rung unlocks when the live rally reaches the configured threshold.'
    : isBothBias
    ? 'Both ladders are armed at once using the same percentage schedule in opposite directions.'
    : 'Each rung unlocks when the live drawdown reaches the configured threshold.';
  const takeProfitLabel = isShortBias ? 'Take Profit Down' : 'Take Profit Up';
  const optionContractsLabel = isShortBias ? 'Call Contracts' : 'Put Contracts';
  const entryScheduleLabel = isShortBias ? 'Rally schedule' : 'Entry schedule';
  const closeBehaviorLabel = isShortBias ? 'Close call with futures' : 'Close put with futures';
  const leaveBehaviorLabel = isShortBias ? 'Leave call after exit' : 'Leave put after exit';
  const hedgeSelectionLabel = config?.hedge_config.enabled
    ? `${config.hedge_config.hedge_otm_pct}% OTM, min ${config.hedge_config.hedge_dte_min_days} DTE`
    : 'Disabled';

  return (
    <div className="overview-shell">
      <section className="hero">
        <div className="hero-copy">
          <span className="hero-kicker">Advantage Price Entry</span>
          <h2>{headline}</h2>
          <p>{description}</p>
          <div className="hero-actions">
            {!status.running ? (
              <button className="button button-primary" onClick={handleStart} disabled={loading}>
                Start Bot
              </button>
            ) : (
              <button className="button button-danger" onClick={handleStop} disabled={loading}>
                Stop Bot
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
              {status.running ? 'Running' : 'Stopped'}
            </div>
            <div className={`mode-chip ${status.dry_run ? 'warn' : 'accent'}`}>
              {status.dry_run ? 'Simulation' : status.testnet ? 'Testnet' : 'Mainnet'}
            </div>
          </div>
          <div className="hero-metric">
            <span>{moveLabel}</span>
            <strong>{currentMove.toFixed(2)}%</strong>
          </div>
          <div className="hero-metric">
            <span>Next entry distance</span>
            <strong>{thresholdGap !== null ? `${thresholdGap.toFixed(2)}%` : 'All levels used'}</strong>
          </div>
          <div className="hero-metric">
            <span>Hedge handling</span>
            <strong>{status.close_hedge_with_future ? 'Close with position' : 'Keep hedge open'}</strong>
          </div>
        </div>
      </section>

      <section className="overview-grid">
        <div className="overview-column overview-column-main">
          <div className="panel">
            <div className="panel-head">
              <div>
                <h3 className="panel-title">Entry Levels</h3>
                <p className="panel-copy">{strategyPanelCopy}</p>
              </div>
            </div>
            {isBothBias ? (
              <div style={{ display: 'grid', gap: '18px' }}>
                <LadderBlock
                  title="Long Ladder"
                  subtitle={`Buy drawdowns on ${status.long_symbol} from the UTC open and hedge with long puts.`}
                  levels={status.long_entry_levels_pct}
                  filledLevels={filledLevelsLong}
                  currentMovePct={currentLongMove}
                />
                <LadderBlock
                  title="Short Ladder"
                  subtitle={`Sell rallies on ${status.short_symbol} from the UTC open and hedge with long calls.`}
                  levels={status.short_entry_levels_pct}
                  filledLevels={filledLevelsShort}
                  currentMovePct={currentShortMove}
                />
              </div>
            ) : (
              <div className="ladder-grid">
                {(isShortBias ? status.short_entry_levels_pct : status.long_entry_levels_pct).map((level, index) => (
                  <LadderPill
                    key={`${level}-${index}`}
                    level={level}
                    filled={isShortBias ? filledLevelsShort.has(index) : filledLevelsLong.has(index)}
                    currentMovePct={isShortBias ? currentShortMove : currentLongMove}
                  />
                ))}
              </div>
            )}
          </div>

          <PriceChart data={chartData} loading={chartLoading} />
          <EquityCurve points={equityPoints} dryRun={status.dry_run} />
        </div>

        <div className="overview-column overview-column-side">
          <div className="panel metrics-panel">
            <h3 className="panel-title">Current Status</h3>
            <div className="metric-stack">
              <div className="metric-row">
                <span>Reference Open</span>
                <strong>{status.daily_open_price ? `$${status.daily_open_price.toFixed(2)}` : 'N/A'}</strong>
              </div>
              {isBothBias && (
                <>
                  <div className="metric-row">
                    <span>Long drawdown ({status.long_symbol})</span>
                    <strong>{currentLongMove.toFixed(2)}%</strong>
                  </div>
                  <div className="metric-row">
                    <span>Short rally ({status.short_symbol})</span>
                    <strong>{currentShortMove.toFixed(2)}%</strong>
                  </div>
                </>
              )}
              <div className="metric-row">
                <span>Current Price</span>
                <strong>{status.current_price ? `${status.symbol} $${status.current_price.toFixed(2)}` : 'N/A'}</strong>
              </div>
              <div className="metric-row">
                <span>Profit Target</span>
                <strong>{takeProfitLabel} {status.target_profit_pct.toFixed(2)}%</strong>
              </div>
              <div className="metric-row">
                <span>Open Entries</span>
                <strong>{status.active_position_sets} / {status.max_position_sets}</strong>
              </div>
              <div className="metric-row">
                <span>Futures Size</span>
                <strong>{status.total_exposure.perp_qty.toFixed(3)}</strong>
              </div>
              <div className="metric-row">
                <span>{optionContractsLabel}</span>
                <strong>{status.total_exposure.option_contracts.toFixed(3)}</strong>
              </div>
            </div>
          </div>

          <div className="panel">
            <h3 className="panel-title">Strategy Settings</h3>
            <div className="detail-list">
              <div>
                <span>Reference price</span>
                <strong>UTC 00:00 open</strong>
              </div>
              <div>
                <span>{entryScheduleLabel}</span>
                <strong>
                  {isShortBias
                    ? `${status.short_entry_levels_pct.join(' / ')}%`
                    : isBothBias
                    ? `Long ${status.long_entry_levels_pct.join(' / ')}% | Short ${status.short_entry_levels_pct.join(' / ')}%`
                    : `${status.long_entry_levels_pct.join(' / ')}%`}
                </strong>
              </div>
              {isBothBias && (
                <div>
                  <span>Direction set</span>
                  <strong>{status.long_symbol} long drawdowns + {status.short_symbol} short rallies</strong>
                </div>
              )}
              <div>
                <span>Hedge selection</span>
                <strong>{hedgeSelectionLabel}</strong>
              </div>
              <div>
                <span>Close behavior</span>
                <strong>{status.close_hedge_with_future ? closeBehaviorLabel : leaveBehaviorLabel}</strong>
              </div>
              <div>
                <span>Account Mode</span>
                <strong>{status.dry_run ? 'Simulation' : status.testnet ? 'Testnet' : 'Mainnet'}</strong>
              </div>
            </div>
          </div>

          <div className="panel">
            <h3 className="panel-title">Performance</h3>
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
