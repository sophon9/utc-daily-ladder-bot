import { EquityPoint } from '../types';

interface EquityCurveProps {
  points: EquityPoint[];
  dryRun: boolean;
}

export default function EquityCurve({ points, dryRun }: EquityCurveProps) {
  if (dryRun) {
    return (
      <div className="panel panel-empty">
        <div>
          <h3 className="panel-title">Equity Curve</h3>
          <p className="panel-copy">History is only recorded while running with live account access.</p>
        </div>
      </div>
    );
  }

  if (points.length < 2) {
    return (
      <div className="panel panel-empty">
        <div>
          <h3 className="panel-title">Equity Curve</h3>
          <p className="panel-copy">Waiting for enough live equity samples to draw a performance curve.</p>
        </div>
      </div>
    );
  }

  const width = 760;
  const height = 280;
  const padding = { top: 18, right: 18, bottom: 28, left: 18 };
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;

  const values = points.map((point) => point.equity);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = Math.max(max - min, 1);
  const yPadding = range * 0.12;

  const xScale = (index: number) => padding.left + (index / Math.max(points.length - 1, 1)) * chartWidth;
  const yScale = (value: number) =>
    padding.top + ((max + yPadding - value) / (range + 2 * yPadding)) * chartHeight;

  const linePath = points.map((point, index) => {
    const x = xScale(index);
    const y = yScale(point.equity);
    return `${index === 0 ? 'M' : 'L'} ${x} ${y}`;
  }).join(' ');

  const areaPath = `${linePath} L ${xScale(points.length - 1)} ${height - padding.bottom} L ${xScale(0)} ${height - padding.bottom} Z`;

  const start = values[0];
  const current = values[values.length - 1];
  const delta = current - start;
  const deltaPct = start > 0 ? (delta / start) * 100 : 0;

  const labels = [
    points[0],
    points[Math.floor(points.length / 2)],
    points[points.length - 1],
  ];

  return (
    <div className="panel">
      <div className="panel-head">
        <div>
          <h3 className="panel-title">Equity Curve</h3>
          <p className="panel-copy">Persisted account equity snapshots from the live trading session.</p>
        </div>
        <div className={`performance-chip ${delta >= 0 ? 'positive' : 'negative'}`}>
          {delta >= 0 ? '+' : ''}{delta.toFixed(2)} USD
          <span>{delta >= 0 ? '+' : ''}{deltaPct.toFixed(2)}%</span>
        </div>
      </div>

      <div className="equity-stats">
        <div>
          <span>Start</span>
          <strong>${start.toFixed(2)}</strong>
        </div>
        <div>
          <span>Current</span>
          <strong>${current.toFixed(2)}</strong>
        </div>
        <div>
          <span>High</span>
          <strong>${max.toFixed(2)}</strong>
        </div>
        <div>
          <span>Low</span>
          <strong>${min.toFixed(2)}</strong>
        </div>
      </div>

      <div className="equity-chart-shell">
        <svg viewBox={`0 0 ${width} ${height}`} className="equity-chart" preserveAspectRatio="none">
          <defs>
            <linearGradient id="equityArea" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" stopColor="rgba(44, 214, 166, 0.32)" />
              <stop offset="100%" stopColor="rgba(44, 214, 166, 0.02)" />
            </linearGradient>
          </defs>

          {[0.2, 0.4, 0.6, 0.8].map((fraction) => {
            const y = padding.top + chartHeight * fraction;
            return (
              <line
                key={fraction}
                x1={padding.left}
                y1={y}
                x2={width - padding.right}
                y2={y}
                stroke="rgba(255,255,255,0.08)"
                strokeDasharray="3 6"
              />
            );
          })}

          <path d={areaPath} fill="url(#equityArea)" />
          <path d={linePath} fill="none" stroke="var(--accent-positive)" strokeWidth="3" strokeLinecap="round" />

          {labels.map((point, index) => {
            const pointIndex = index === 0 ? 0 : index === 1 ? Math.floor(points.length / 2) : points.length - 1;
            const x = xScale(pointIndex);
            const y = yScale(point.equity);
            return (
              <g key={`${point.timestamp}-${index}`}>
                <circle cx={x} cy={y} r="4.5" fill="var(--accent-positive)" />
                <text x={x} y={height - 6} textAnchor="middle" className="equity-axis-label">
                  {new Date(point.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
    </div>
  );
}
