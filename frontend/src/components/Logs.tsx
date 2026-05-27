import React from 'react';

interface LogResponse {
  lines: string[];
  content: string;
  path: string;
  available: boolean;
  line_count?: number;
  updated_at?: number;
}

export default function Logs() {
  const [logs, setLogs] = React.useState<LogResponse | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [refreshing, setRefreshing] = React.useState(false);
  const [lineCount, setLineCount] = React.useState(50);

  const fetchLogs = React.useCallback(async (showLoading: boolean) => {
    if (showLoading) {
      setLoading(true);
    } else {
      setRefreshing(true);
    }

    try {
      const response = await fetch(`/api/logs?lines=${lineCount}`);
      if (!response.ok) {
        throw new Error('Failed to load logs');
      }
      const data = await response.json();
      setLogs(data);
    } catch (err) {
      console.error('Failed to fetch logs:', err);
      setLogs({
        lines: [],
        content: 'Failed to load logs.',
        path: 'logs/ema_bot.log',
        available: false,
      });
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [lineCount]);

  React.useEffect(() => {
    fetchLogs(true);
  }, [fetchLogs]);

  React.useEffect(() => {
    const interval = setInterval(() => {
      fetchLogs(false);
    }, 5000);

    return () => clearInterval(interval);
  }, [fetchLogs]);

  return (
    <div className="card">
      <div className="flex justify-between items-center" style={{ marginBottom: '16px', gap: '12px', flexWrap: 'wrap' }}>
        <div>
          <h2 className="card-title" style={{ marginBottom: '4px' }}>Logs</h2>
          <div className="text-muted" style={{ fontSize: '12px' }}>
            {logs?.path ?? 'logs/ema_bot.log'}
          </div>
        </div>

        <div className="flex items-center" style={{ gap: '8px', flexWrap: 'wrap' }}>
          <label className="text-muted" style={{ fontSize: '12px' }}>
            Lines
          </label>
          <select
            value={lineCount}
            onChange={(e) => setLineCount(parseInt(e.target.value, 10))}
            style={{
              backgroundColor: 'var(--bg-secondary)',
              color: 'var(--text-primary)',
              border: '1px solid var(--border-color)',
              borderRadius: '6px',
              padding: '8px 10px',
            }}
          >
            <option value={50}>50</option>
            <option value={100}>100</option>
            <option value={200}>200</option>
            <option value={500}>500</option>
            <option value={1000}>1000</option>
          </select>
          <button
            className="button secondary"
            onClick={() => fetchLogs(false)}
            disabled={loading || refreshing}
          >
            {refreshing ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>
      </div>

      {loading ? (
        <p className="text-muted">Loading logs...</p>
      ) : !logs?.available ? (
        <p className="text-muted">{logs?.content ?? 'Log file not available.'}</p>
      ) : (
        <>
          <div className="text-muted" style={{ fontSize: '12px', marginBottom: '12px' }}>
            Showing last {logs.line_count ?? logs.lines.length} lines
            {logs.updated_at ? ` | Updated ${new Date(logs.updated_at * 1000).toLocaleString()}` : ''}
          </div>
          <pre
            style={{
              backgroundColor: 'var(--bg-tertiary)',
              color: 'var(--text-primary)',
              padding: '16px',
              borderRadius: '8px',
              overflow: 'auto',
              maxHeight: '70vh',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
              fontSize: '12px',
              lineHeight: '1.5',
              margin: 0,
            }}
          >
            <code>{logs.content || 'Log file is empty.'}</code>
          </pre>
        </>
      )}
    </div>
  );
}
