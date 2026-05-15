interface Candle {
  timestamp: number;
  close: number;
  datetime: string;
}

interface ChartData {
  candles: Candle[];
  reference_values: number[];
  reference_label: string;
}

interface PriceChartProps {
  data: ChartData | null;
  loading: boolean;
}

export default function PriceChart({ data, loading }: PriceChartProps) {
  if (loading) {
    return <div className="panel panel-empty">Loading price context...</div>;
  }

  if (!data || data.candles.length === 0) {
    return <div className="panel panel-empty">No chart data available.</div>;
  }

  const { candles, reference_values, reference_label } = data;
  const width = 760;
  const height = 320;
  const padding = { top: 18, right: 18, bottom: 28, left: 18 };
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;

  const prices = candles.map((candle) => candle.close);
  const allValues = [...prices, ...reference_values];
  const minPrice = Math.min(...allValues);
  const maxPrice = Math.max(...allValues);
  const range = Math.max(maxPrice - minPrice, 1);
  const yPadding = range * 0.12;

  const xScale = (index: number) => padding.left + (index / Math.max(candles.length - 1, 1)) * chartWidth;
  const yScale = (price: number) => padding.top + ((maxPrice + yPadding - price) / (range + 2 * yPadding)) * chartHeight;

  const pricePath = candles.map((candle, index) => {
    const x = xScale(index);
    const y = yScale(candle.close);
    return `${index === 0 ? 'M' : 'L'} ${x} ${y}`;
  }).join(' ');

  const referencePath = reference_values.map((value, index) => {
    const x = xScale(index);
    const y = yScale(value);
    return `${index === 0 ? 'M' : 'L'} ${x} ${y}`;
  }).join(' ');

  const currentPrice = prices[prices.length - 1];
  const currentReference = reference_values[reference_values.length - 1] || 0;
  const drawdownPct = currentReference > 0 ? ((currentReference - currentPrice) / currentReference) * 100 : 0;

  const timeMarkers = [
    candles[0],
    candles[Math.floor(candles.length / 2)],
    candles[candles.length - 1],
  ];

  return (
    <div className="panel">
      <div className="panel-head">
        <div>
          <h3 className="panel-title">Price vs Session Anchor</h3>
          <p className="panel-copy">Visual check of the live market versus the UTC daily-open reference line.</p>
        </div>
        <div className="chart-callouts">
          <div>
            <span>Price</span>
            <strong>${currentPrice.toFixed(2)}</strong>
          </div>
          <div>
            <span>{reference_label}</span>
            <strong>${currentReference.toFixed(2)}</strong>
          </div>
          <div>
            <span>Drawdown</span>
            <strong>{drawdownPct.toFixed(2)}%</strong>
          </div>
        </div>
      </div>

      <div className="price-chart-shell">
        <svg viewBox={`0 0 ${width} ${height}`} className="price-chart" preserveAspectRatio="none">
          <defs>
            <linearGradient id="priceArea" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" stopColor="rgba(33, 147, 176, 0.28)" />
              <stop offset="100%" stopColor="rgba(33, 147, 176, 0.02)" />
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

          <path
            d={`${pricePath} L ${xScale(candles.length - 1)} ${height - padding.bottom} L ${xScale(0)} ${height - padding.bottom} Z`}
            fill="url(#priceArea)"
          />
          <path d={referencePath} fill="none" stroke="var(--accent-warning)" strokeWidth="2" strokeDasharray="8 10" />
          <path d={pricePath} fill="none" stroke="var(--accent-primary)" strokeWidth="3" strokeLinecap="round" />

          <circle cx={xScale(candles.length - 1)} cy={yScale(currentPrice)} r="4.5" fill="var(--accent-primary)" />
          <circle cx={xScale(candles.length - 1)} cy={yScale(currentReference)} r="4.5" fill="var(--accent-warning)" />

          {timeMarkers.map((marker, index) => {
            const pointIndex = index === 0 ? 0 : index === 1 ? Math.floor(candles.length / 2) : candles.length - 1;
            return (
              <text
                key={`${marker.timestamp}-${index}`}
                x={xScale(pointIndex)}
                y={height - 6}
                textAnchor="middle"
                className="equity-axis-label"
              >
                {new Date(marker.datetime).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </text>
            );
          })}
        </svg>
      </div>
    </div>
  );
}
