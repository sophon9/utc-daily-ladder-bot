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
    return (
      <div className="card" style={{ minHeight: '300px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div className="text-muted">Loading chart...</div>
      </div>
    );
  }

  if (!data || !data.candles || data.candles.length === 0) {
    return (
      <div className="card" style={{ minHeight: '300px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div className="text-muted">No chart data available</div>
      </div>
    );
  }

  const { candles, reference_values, reference_label } = data;
  const width = 800;
  const height = 300;
  const padding = { top: 20, right: 80, bottom: 40, left: 60 };
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;

  const prices = candles.map((c) => c.close);
  const allValues = [...prices, ...reference_values];
  const minPrice = Math.min(...allValues);
  const maxPrice = Math.max(...allValues);
  const priceRange = Math.max(maxPrice - minPrice, 1);
  const pricePadding = priceRange * 0.1;

  const xScale = (index: number) => padding.left + (index / Math.max(candles.length - 1, 1)) * chartWidth;
  const yScale = (price: number) => padding.top + ((maxPrice + pricePadding - price) / (priceRange + 2 * pricePadding)) * chartHeight;

  const pricePath = candles.map((candle, index) => {
    const x = xScale(index);
    const y = yScale(candle.close);
    return index === 0 ? `M ${x} ${y}` : `L ${x} ${y}`;
  }).join(' ');

  let referencePath = '';
  if (reference_values.length > 0) {
    referencePath = reference_values.map((value, index) => {
      const x = xScale(index);
      const y = yScale(value);
      return index === 0 ? `M ${x} ${y}` : `L ${x} ${y}`;
    }).join(' ');
  }

  const currentPrice = prices[prices.length - 1];
  const currentReference = reference_values[reference_values.length - 1] || 0;
  const drawdownPct = currentReference > 0
    ? ((currentReference - currentPrice) / currentReference) * 100
    : 0;

  const numTicks = 5;
  const yTicks = Array.from({ length: numTicks }, (_, i) => {
    const price = minPrice - pricePadding + (priceRange + 2 * pricePadding) * (i / (numTicks - 1));
    return price;
  }).reverse();

  return (
    <div className="card">
      <h2 className="card-title">Price vs UTC Daily Open</h2>

      <div style={{ marginBottom: '15px', display: 'flex', gap: '15px', alignItems: 'center', flexWrap: 'wrap' }}>
        <div>
          <span style={{ color: '#4fc3f7' }}>●</span> Current Price: <strong>${currentPrice.toFixed(2)}</strong>
        </div>
        <div>
          <span style={{ color: '#ffb74d' }}>●</span> {reference_label}: <strong>${currentReference.toFixed(2)}</strong>
        </div>
        <div>
          <span className={drawdownPct >= 0 ? 'negative' : 'positive'}>
            Drawdown: {drawdownPct >= 0 ? '' : '+'}{drawdownPct.toFixed(2)}%
          </span>
        </div>
      </div>

      <div style={{ overflowX: 'auto' }}>
        <svg width={width} height={height} style={{ display: 'block', margin: '0 auto' }}>
          {yTicks.map((price, i) => (
            <g key={i}>
              <line
                x1={padding.left}
                y1={yScale(price)}
                x2={width - padding.right}
                y2={yScale(price)}
                stroke="#2a2a2a"
                strokeWidth="1"
                strokeDasharray="2,2"
              />
              <text
                x={padding.left - 10}
                y={yScale(price)}
                textAnchor="end"
                alignmentBaseline="middle"
                fill="#999"
                fontSize="12"
              >
                ${price.toFixed(0)}
              </text>
            </g>
          ))}

          {referencePath && (
            <path d={referencePath} fill="none" stroke="#ffb74d" strokeWidth="2" />
          )}

          <path d={pricePath} fill="none" stroke="#4fc3f7" strokeWidth="2" />

          <circle cx={xScale(candles.length - 1)} cy={yScale(currentPrice)} r="4" fill="#4fc3f7" />
          {reference_values.length > 0 && (
            <circle cx={xScale(candles.length - 1)} cy={yScale(currentReference)} r="4" fill="#ffb74d" />
          )}

          {[0, Math.floor(candles.length / 2), candles.length - 1].map((i) => {
            const candle = candles[i];
            const time = new Date(candle.datetime).toLocaleTimeString('en-US', {
              hour: '2-digit',
              minute: '2-digit',
            });
            return (
              <text
                key={i}
                x={xScale(i)}
                y={height - padding.bottom + 20}
                textAnchor="middle"
                fill="#999"
                fontSize="12"
              >
                {time}
              </text>
            );
          })}
        </svg>
      </div>
    </div>
  );
}
