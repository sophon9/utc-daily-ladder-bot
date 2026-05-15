// Positions tab component

import React from 'react';
import { PositionSet } from '../types';
import { useAPI } from '../hooks/useBot';

interface PositionsProps {
  positions: PositionSet[];
}

export default function Positions({ positions }: PositionsProps) {
  const api = useAPI();
  const [loading, setLoading] = React.useState<string | null>(null);
  const priceValueStyle = { fontSize: '14px', fontWeight: '700' } as const;

  const handleClosePosition = async (setId: string) => {
    if (!confirm(`Close position set ${setId}?`)) return;

    setLoading(setId);
    try {
      await api.closePosition(setId);
    } catch (err) {
      console.error('Failed to close position:', err);
      alert('Failed to close position');
    } finally {
      setLoading(null);
    }
  };

  const handleRemovePosition = async (setId: string) => {
    if (!confirm(`Remove closed position ${setId} from the list?`)) return;

    setLoading(setId);
    try {
      await api.removePosition(setId);
    } catch (err) {
      console.error('Failed to remove position:', err);
      alert('Failed to remove position');
    } finally {
      setLoading(null);
    }
  };

  const handleRemoveStalePosition = async (setId: string) => {
    if (!confirm(
      `Remove stale position ${setId} from local bot state?\n\nUse this only if the position was already closed manually on the exchange and is stuck in the UI.`
    )) return;

    setLoading(setId);
    try {
      await api.removePosition(setId, true);
    } catch (err) {
      console.error('Failed to remove stale position:', err);
      alert('Failed to remove stale position');
    } finally {
      setLoading(null);
    }
  };

  const getStateBadgeClass = (state: string) => {
    switch (state) {
      case 'open': return 'success';
      case 'opening': return 'info';
      case 'closing': return 'warning';
      case 'hedge_only': return 'info';
      case 'closed': return 'badge secondary';
      case 'error': return 'error';
      default: return 'info';
    }
  };

  const activePositions = positions.filter(p => ['open', 'opening', 'hedge_only'].includes(p.state));
  const closedPositions = positions
    .filter(p => ['closed', 'error', 'closing'].includes(p.state))
    .sort((a, b) => {
      const aTime = new Date(a.closed_at ?? a.created_at).getTime();
      const bTime = new Date(b.closed_at ?? b.created_at).getTime();
      return bTime - aTime;
    });

  return (
    <div>
      {/* Active positions */}
      <div className="card">
        <div className="flex justify-between items-center" style={{ marginBottom: '16px' }}>
          <h2 className="card-title" style={{ marginBottom: 0 }}>Active Positions</h2>
          {activePositions.length > 0 && (
            <button
              className="button danger"
              onClick={async () => {
                if (!confirm('Close ALL active positions?')) return;
                try {
                  await api.closeAllPositions();
                } catch (err) {
                  alert('Failed to close all positions');
                }
              }}
            >
              Close All
            </button>
          )}
        </div>

        {activePositions.length === 0 ? (
          <p className="text-muted">No active positions</p>
        ) : (
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>Set ID</th>
                  <th>Level</th>
                  <th>State</th>
                  <th>Perp</th>
                  <th>Hedge Put</th>
                  <th>Combined PnL</th>
                  <th>Target</th>
                  <th>Open Time</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {activePositions.map((ps) => (
                  <tr key={ps.set_id}>
                    <td><code>{ps.set_id}</code></td>
                    <td>{ps.trigger_pct !== undefined ? `${ps.trigger_pct}%` : '-'}</td>
                    <td>
                      <span className={`badge ${getStateBadgeClass(ps.state)}`}>
                        {ps.state}
                      </span>
                    </td>
                    <td>
                      {ps.perp_leg ? (
                        <div>
                          <div className="text-muted" style={{ fontSize: '11px' }}>
                            {ps.perp_leg.side.toUpperCase()}
                          </div>
                          <div style={{ fontSize: '13px', fontWeight: '500' }}>
                            Size: {ps.perp_leg.filled_qty.toFixed(3)} {ps.perp_leg.symbol.replace('USDT', '').replace('USDC', '')}
                          </div>
                          <div className="text-muted" style={{ fontSize: '11px' }}>
                            Entry: <span style={priceValueStyle}>${ps.perp_leg.entry_price?.toFixed(2)}</span>
                          </div>
                          <div className={ps.perp_leg.unrealized_pnl >= 0 ? 'text-success' : 'text-error'} style={{ fontSize: '12px', fontWeight: '600' }}>
                            ${ps.perp_leg.unrealized_pnl.toFixed(2)}
                          </div>
                        </div>
                      ) : '-'}
                    </td>
                    <td>
                      {ps.option_leg ? (
                        <div>
                          <div className="text-muted" style={{ fontSize: '11px' }}>
                            {ps.option_leg.side.toUpperCase()} {ps.option_leg.option_type}
                          </div>
                          <div style={{ fontSize: '13px', fontWeight: '500' }}>
                            Size: {ps.option_leg.filled_qty.toFixed(3)}
                          </div>
                          <div className="text-muted" style={{ fontSize: '11px' }}>
                            K={ps.option_leg.strike}
                          </div>
                          <div className="text-muted" style={{ fontSize: '11px' }}>
                            Expiry: {ps.option_leg.expiry ?? '-'}
                          </div>
                          <div className="text-muted" style={{ fontSize: '11px' }}>
                            Entry: <span style={priceValueStyle}>${ps.option_leg.entry_price?.toFixed(2)}</span>
                          </div>
                          <div className={ps.option_leg.unrealized_pnl >= 0 ? 'text-success' : 'text-error'} style={{ fontSize: '12px', fontWeight: '600' }}>
                            ${ps.option_leg.unrealized_pnl.toFixed(2)}
                          </div>
                        </div>
                      ) : '-'}
                    </td>
                    <td>
                      <strong className={ps.combined_pnl >= 0 ? 'text-success' : 'text-error'}>
                        ${ps.combined_pnl.toFixed(2)}
                      </strong>
                    </td>
                    <td>
                      <div style={{ fontSize: '12px', lineHeight: '1.6' }}>
                        <div>
                          <strong>{ps.target_profit_pct.toFixed(2)}%</strong>
                        </div>
                        <div className="text-muted" style={{ fontSize: '11px' }}>
                          Target Price: {ps.target_exit_price ? <span style={priceValueStyle}>${ps.target_exit_price.toFixed(2)}</span> : '-'}
                        </div>
                      </div>
                    </td>
                    <td>
                      {ps.opened_at ? new Date(ps.opened_at).toLocaleString() : '-'}
                    </td>
                    <td>
                      <div className="button-group">
                        {ps.state === 'open' && (
                          <button
                            className="button danger"
                            onClick={() => handleClosePosition(ps.set_id)}
                            disabled={loading === ps.set_id}
                          >
                            Close
                          </button>
                        )}
                        <button
                          className="button secondary"
                          onClick={() => handleRemoveStalePosition(ps.set_id)}
                          disabled={loading === ps.set_id}
                          title="Remove stale local record when the exchange position is already gone"
                        >
                          Remove Stale
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Recent closed positions */}
      {closedPositions.length > 0 && (
        <div className="card">
          <h2 className="card-title">Recent Closed Positions</h2>
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>Set ID</th>
                  <th>Bias</th>
                  <th>State</th>
                  <th>Perp (Entry / Exit / Fee)</th>
                  <th>Option (Entry / Exit / Fee)</th>
                  <th>Final PnL</th>
                  <th>Opened</th>
                  <th>Closed</th>
                  <th>Duration</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {closedPositions.slice(0, 10).map((ps) => {
                  const duration = ps.opened_at && ps.closed_at
                    ? ((new Date(ps.closed_at).getTime() - new Date(ps.opened_at).getTime()) / 60000).toFixed(1)
                    : '-';

                  // Perp fee: 0.05% per side (entry + exit)
                  const perpFee = ps.perp_leg && ps.perp_leg.filled && ps.perp_leg.entry_price
                    ? ps.perp_leg.entry_price * ps.perp_leg.filled_qty * 0.0005
                      + (ps.perp_leg.exit_price ?? 0) * ps.perp_leg.filled_qty * 0.0005
                    : null;

                  // Option fee: 0.02% of strike per side (entry + exit)
                  const optFee = ps.option_leg && ps.option_leg.filled && ps.option_leg.strike
                    ? ps.option_leg.strike * ps.option_leg.filled_qty * 0.0002
                      + ps.option_leg.strike * ps.option_leg.filled_qty * 0.0002
                    : null;

                  return (
                    <tr key={ps.set_id}>
                      <td><code>{ps.set_id}</code></td>
                      <td>{ps.bias.toUpperCase()}</td>
                      <td>
                        <span className={`badge ${getStateBadgeClass(ps.state)}`}>
                          {ps.state}
                        </span>
                      </td>

                      {/* Perp leg: entry / exit / fee */}
                      <td>
                        {ps.perp_leg && ps.perp_leg.filled ? (
                          <div style={{ fontSize: '12px', lineHeight: '1.6' }}>
                            <div>
                              <span className="text-muted">Entry </span>
                              <strong style={priceValueStyle}>${ps.perp_leg.entry_price?.toFixed(2) ?? '-'}</strong>
                            </div>
                            <div>
                              <span className="text-muted">Exit  </span>
                              <strong style={priceValueStyle}>${ps.perp_leg.exit_price?.toFixed(2) ?? '-'}</strong>
                            </div>
                            <div style={{ color: 'var(--accent-error)' }}>
                              Fee −${perpFee?.toFixed(4) ?? '-'}
                            </div>
                          </div>
                        ) : <span className="text-muted">—</span>}
                      </td>

                      {/* Option leg: strike / entry / exit / fee */}
                      <td>
                        {ps.option_leg && ps.option_leg.filled ? (
                          <div style={{ fontSize: '12px', lineHeight: '1.6' }}>
                            <div className="text-muted" style={{ fontSize: '11px' }}>
                              K={ps.option_leg.strike} {ps.option_leg.option_type}
                            </div>
                            <div className="text-muted" style={{ fontSize: '11px' }}>
                              Expiry: {ps.option_leg.expiry ?? '-'}
                            </div>
                            <div>
                              <span className="text-muted">Entry </span>
                              <strong style={priceValueStyle}>${ps.option_leg.entry_price?.toFixed(4) ?? '-'}</strong>
                            </div>
                            <div>
                              <span className="text-muted">Exit  </span>
                              <strong style={priceValueStyle}>${ps.option_leg.exit_price?.toFixed(4) ?? '-'}</strong>
                            </div>
                            <div style={{ color: 'var(--accent-error)' }}>
                              Fee −${optFee?.toFixed(4) ?? '-'}
                            </div>
                          </div>
                        ) : <span className="text-muted">—</span>}
                      </td>

                      <td>
                        <strong className={ps.combined_pnl >= 0 ? 'text-success' : 'text-error'}>
                          ${ps.combined_pnl.toFixed(2)}
                        </strong>
                      </td>
                      <td className="text-muted" style={{ fontSize: '12px' }}>
                        {ps.opened_at ? new Date(ps.opened_at).toLocaleString() : '-'}
                      </td>
                      <td className="text-muted" style={{ fontSize: '12px' }}>
                        {ps.closed_at ? new Date(ps.closed_at).toLocaleString() : '-'}
                      </td>
                      <td>{duration} min</td>
                      <td>
                        <button
                          className="button danger"
                          onClick={() => handleRemovePosition(ps.set_id)}
                          disabled={loading === ps.set_id}
                        >
                          Remove
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
