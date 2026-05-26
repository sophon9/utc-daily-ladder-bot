import React, { useEffect, useState } from 'react';
import { BotConfig, HedgeConfig } from '../types';
import { useAPI } from '../hooks/useBot';

type SubTab = 'strategy' | 'hedge' | 'system';

function parseLevels(raw: string): number[] {
  return raw
    .split(',')
    .map((value) => parseFloat(value.trim()))
    .filter((value) => Number.isFinite(value) && value > 0)
    .sort((a, b) => a - b);
}

export default function Config() {
  const api = useAPI();
  const [config, setConfig] = useState<BotConfig | null>(null);
  const [longEntryLevelsInput, setLongEntryLevelsInput] = useState('');
  const [shortEntryLevelsInput, setShortEntryLevelsInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [activeSubTab, setActiveSubTab] = useState<SubTab>('strategy');

  useEffect(() => {
    loadConfig();
  }, []);

  const loadConfig = async () => {
    setLoading(true);
    try {
      const cfg = await api.getConfig();
      setConfig(cfg);
      setLongEntryLevelsInput(cfg.long_entry_levels_pct.join(', '));
      setShortEntryLevelsInput(cfg.short_entry_levels_pct.join(', '));
    } catch (err) {
      console.error('Failed to load config:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    if (!config) return;

    setSaving(true);
    try {
      const nextConfig = {
        ...config,
        long_entry_levels_pct: parseLevels(longEntryLevelsInput),
        short_entry_levels_pct: parseLevels(shortEntryLevelsInput),
      };
      await api.updateConfig(nextConfig);
      await loadConfig();
    } catch (err) {
      console.error('Failed to save config:', err);
      alert('Failed to save configuration');
    } finally {
      setSaving(false);
    }
  };

  const updateField = (field: keyof BotConfig, value: any) => {
    if (!config) return;
    const nextConfig = { ...config, [field]: value };
    if (field === 'bias' && (value === 'short' || value === 'both') && config.short_symbol === 'ETHUSDT') {
      nextConfig.short_symbol = 'ETHPERP';
    }
    setConfig(nextConfig);
  };

  const updateHedgeField = (field: keyof HedgeConfig, value: any) => {
    if (!config) return;
    setConfig({
      ...config,
      hedge_config: { ...config.hedge_config, [field]: value },
    });
  };

  if (loading || !config) {
    return <div className="card">Loading configuration...</div>;
  }

  const isShortBias = config.bias === 'short';
  const isBothBias = config.bias === 'both';
  const triggerDirectionCopy = isShortBias
    ? 'Configure the rally ladder used for short entries above the UTC 00:00 daily open.'
    : isBothBias
    ? 'Configure independent drawdown and rally ladders for simultaneous long and short monitoring.'
    : 'Configure the drawdown ladder used for long entries below the UTC 00:00 daily open.';
  const takeProfitCopy = isShortBias
    ? 'Futures leg exits when its mark price falls by this percent from entry.'
    : isBothBias
    ? 'Long entries exit on moves up from entry. Short entries exit on moves down from entry.'
    : 'Futures leg exits when its mark price rises by this percent from entry.';
  const hedgeLabel = isShortBias ? 'Enable Long Call Hedge' : isBothBias ? 'Enable Mirrored Option Hedges' : 'Enable Long Put Hedge';
  const hedgeDistanceCopy = isShortBias
    ? 'Strike must be at least this far above spot.'
    : isBothBias
    ? 'Long ladders use puts below spot. Short ladders use calls above spot by this same distance.'
    : 'Strike must be at least this far below spot.';
  const closeHedgeCopy = isShortBias
    ? 'If disabled, the bot leaves the call open and the position set moves to `hedge_only`.'
    : isBothBias
    ? 'If disabled, the bot leaves the hedge option open after either long or short futures exits.'
    : 'If disabled, the bot leaves the put open and the position set moves to `hedge_only`.';

  const subTabStyle = (tab: SubTab): React.CSSProperties => ({
    padding: '8px 20px',
    background: 'none',
    border: 'none',
    borderBottom: activeSubTab === tab ? '2px solid var(--accent-primary)' : '2px solid transparent',
    color: activeSubTab === tab ? 'var(--accent-primary)' : 'var(--text-secondary)',
    fontSize: '14px',
    cursor: 'pointer',
    transition: 'all 0.2s',
    whiteSpace: 'nowrap',
  });

  return (
    <div>
      <div className="card">
        <h2 className="card-title">Bot Configuration</h2>
        <p className="text-muted" style={{ marginBottom: '16px' }}>
          Stop the bot before changing configuration.
        </p>

        <div style={{ display: 'flex', gap: '4px', marginBottom: '24px', borderBottom: '1px solid var(--border-color)' }}>
          <button style={subTabStyle('strategy')} onClick={() => setActiveSubTab('strategy')}>
            Strategy
          </button>
          <button style={subTabStyle('hedge')} onClick={() => setActiveSubTab('hedge')}>
            Hedge
          </button>
          <button style={subTabStyle('system')} onClick={() => setActiveSubTab('system')}>
            System
          </button>
        </div>

        {activeSubTab === 'strategy' && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px' }}>
            <div>
              <h3 style={{ marginBottom: '16px', fontSize: '15px', color: 'var(--text-secondary)' }}>Entry Ladders</h3>

              <div className="form-group">
                <label className="form-label">Mode</label>
                <select
                  className="form-select"
                  value={config.bias}
                  onChange={(e) => updateField('bias', e.target.value as any)}
                >
                  <option value="long">Long Ladder Enabled</option>
                  <option value="short">Short Ladder Enabled</option>
                  <option value="both">Both Sides Enabled</option>
                  <option value="off">Off</option>
                </select>
              </div>

              <div className="form-group">
                <label className="form-label">Long Entry Levels (%)</label>
                <input
                  type="text"
                  className="form-input"
                  value={longEntryLevelsInput}
                  onChange={(e) => setLongEntryLevelsInput(e.target.value)}
                  placeholder="1, 2, 3"
                />
                <small className="text-muted" style={{ fontSize: '12px', marginTop: '4px', display: 'block' }}>
                  Drawdown levels below the UTC 00:00 daily open for long futures + long put entries.
                </small>
              </div>

              <div className="form-group">
                <label className="form-label">Short Entry Levels (%)</label>
                <input
                  type="text"
                  className="form-input"
                  value={shortEntryLevelsInput}
                  onChange={(e) => setShortEntryLevelsInput(e.target.value)}
                  placeholder="1, 2, 3"
                />
                <small className="text-muted" style={{ fontSize: '12px', marginTop: '4px', display: 'block' }}>
                  Rally levels above the UTC 00:00 daily open for short futures + long call entries.
                </small>
              </div>

              <p className="text-muted" style={{ fontSize: '12px', marginTop: '-4px' }}>
                {triggerDirectionCopy}
              </p>

              <div className="form-group">
                <label className="form-label">Take Profit (%)</label>
                <input
                  type="number"
                  step="0.01"
                  className="form-input"
                  value={config.target_profit_pct}
                  onChange={(e) => updateField('target_profit_pct', parseFloat(e.target.value))}
                />
                <small className="text-muted" style={{ fontSize: '12px', marginTop: '4px', display: 'block' }}>
                  {takeProfitCopy}
                </small>
              </div>
            </div>

            <div>
              <h3 style={{ marginBottom: '16px', fontSize: '15px', color: 'var(--text-secondary)' }}>Sizing & Risk</h3>

              <div className="form-group">
                <label className="form-label">Per Entry Futures Size</label>
                <input
                  type="number"
                  step="0.01"
                  className="form-input"
                  value={config.perp_qty}
                  onChange={(e) => updateField('perp_qty', parseFloat(e.target.value))}
                />
                <small className="text-muted" style={{ fontSize: '12px', marginTop: '4px', display: 'block' }}>
                  The hedge option uses the same numeric size.
                </small>
              </div>

              <div className="form-group">
                <label className="form-label">Max Loss ($)</label>
                <input
                  type="number"
                  min="0"
                  className="form-input"
                  value={config.max_loss_usd ?? ''}
                  placeholder="Empty = disabled"
                  onChange={(e) => updateField('max_loss_usd', e.target.value !== '' ? parseFloat(e.target.value) : null)}
                />
              </div>

              <div className="form-group">
                <label className="form-label">Max Position Sets</label>
                <input
                  type="number"
                  min="1"
                  max="20"
                  className="form-input"
                  value={config.max_position_sets}
                  onChange={(e) => updateField('max_position_sets', parseInt(e.target.value))}
                />
              </div>

              <div className="form-group">
                <label className="form-label">Cooldown (minutes)</label>
                <input
                  type="number"
                  min="0"
                  className="form-input"
                  value={config.cooldown_minutes}
                  onChange={(e) => updateField('cooldown_minutes', parseInt(e.target.value))}
                />
              </div>
            </div>
          </div>
        )}

        {activeSubTab === 'hedge' && (
          <div style={{ maxWidth: '640px', opacity: config.hedge_config.enabled ? 1 : 0.9 }}>
            <div className="form-group">
              <label className="form-label">
                <input
                  type="checkbox"
                  checked={config.hedge_config.enabled}
                  onChange={(e) => updateHedgeField('enabled', e.target.checked)}
                  style={{ marginRight: '8px' }}
                />
                {hedgeLabel}
              </label>
            </div>

            <div className="form-group">
              <label className="form-label">Minimum OTM Distance (%)</label>
              <input
                type="number"
                step="0.1"
                className="form-input"
                value={config.hedge_config.hedge_otm_pct}
                onChange={(e) => updateHedgeField('hedge_otm_pct', parseFloat(e.target.value))}
              />
              <small className="text-muted" style={{ fontSize: '12px', marginTop: '4px', display: 'block' }}>
                {hedgeDistanceCopy}
              </small>
            </div>

            <div className="form-group">
              <label className="form-label">Min DTE (days)</label>
              <input
                type="number"
                className="form-input"
                value={config.hedge_config.hedge_dte_min_days}
                onChange={(e) => updateHedgeField('hedge_dte_min_days', parseInt(e.target.value))}
              />
            </div>

            <div className="form-group">
              <label className="form-label">Fallback Slippage (bps)</label>
              <input
                type="number"
                className="form-input"
                value={config.hedge_config.slippage_bps}
                onChange={(e) => updateHedgeField('slippage_bps', parseInt(e.target.value))}
              />
            </div>

            <div className="form-group">
              <label className="form-label">
                <input
                  type="checkbox"
                  checked={config.hedge_config.close_with_future}
                  onChange={(e) => updateHedgeField('close_with_future', e.target.checked)}
                  style={{ marginRight: '8px' }}
                />
                Close Hedge When Futures Exit
              </label>
              <small className="text-muted" style={{ fontSize: '12px', marginTop: '4px', display: 'block' }}>
                {closeHedgeCopy}
              </small>
            </div>
          </div>
        )}

        {activeSubTab === 'system' && (
          <div style={{ maxWidth: '480px' }}>
            <div className="form-group">
              <label className="form-label">Bot Name</label>
              <input
                type="text"
                className="form-input"
                value={config.bot_name}
                onChange={(e) => updateField('bot_name', e.target.value)}
                placeholder="Advantage Price Bot"
              />
            </div>

            <div className="form-group">
              <label className="form-label">Account Name</label>
              <input
                type="text"
                className="form-input"
                value={config.account_name}
                onChange={(e) => updateField('account_name', e.target.value)}
                placeholder="Primary Account"
              />
              <small className="text-muted" style={{ fontSize: '12px', marginTop: '4px', display: 'block' }}>
                Display-only label shown at the top of the dashboard.
              </small>
            </div>

            <div className="form-group">
              <label className="form-label">Long Symbol</label>
              <input
                type="text"
                className="form-input"
                value={config.long_symbol}
                onChange={(e) => updateField('long_symbol', e.target.value.toUpperCase())}
                placeholder="ETHUSDT"
              />
            </div>

            <div className="form-group">
              <label className="form-label">Short Symbol</label>
              <input
                type="text"
                className="form-input"
                value={config.short_symbol}
                onChange={(e) => updateField('short_symbol', e.target.value.toUpperCase())}
                placeholder="ETHPERP"
              />
            </div>

            <div className="form-group">
              <label className="form-label">Poll Interval (seconds)</label>
              <input
                type="number"
                className="form-input"
                value={config.poll_interval_seconds}
                onChange={(e) => updateField('poll_interval_seconds', parseInt(e.target.value))}
              />
            </div>

            <div className="form-group">
              <label className="form-label">Log Level</label>
              <select
                className="form-select"
                value={config.log_level}
                onChange={(e) => updateField('log_level', e.target.value as any)}
              >
                <option value="DEBUG">Debug</option>
                <option value="INFO">Info</option>
                <option value="WARNING">Warning</option>
                <option value="ERROR">Error</option>
              </select>
            </div>

            <div className="form-group">
              <label className="form-label">
                <input
                  type="checkbox"
                  checked={config.dry_run}
                  onChange={(e) => updateField('dry_run', e.target.checked)}
                  style={{ marginRight: '8px' }}
                />
                Dry Run Mode
              </label>
            </div>

            <div className="form-group">
              <label className="form-label">
                <input
                  type="checkbox"
                  checked={config.use_testnet}
                  onChange={(e) => updateField('use_testnet', e.target.checked)}
                  style={{ marginRight: '8px' }}
                />
                Use Testnet
              </label>
            </div>
          </div>
        )}

        <div className="mt-lg">
          <button className="button success" onClick={handleSave} disabled={saving}>
            {saving ? 'Saving...' : 'Save Configuration'}
          </button>
        </div>
      </div>
    </div>
  );
}
