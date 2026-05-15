import { useState } from 'react';
import { useWebSocket } from './hooks/useBot';
import Overview from './components/Overview';
import Positions from './components/Positions';
import Config from './components/Config';
import Logs from './components/Logs';
import './styles/app.css';

type TabType = 'overview' | 'positions' | 'config' | 'logs';

function App() {
  const { status, positions, connected } = useWebSocket();
  const [activeTab, setActiveTab] = useState<TabType>('overview');

  return (
    <div className="app">
      <header className="header">
        <h1>Daily Ladder Bot</h1>
        <div className="connection-status">
          <span className={`status-dot ${connected ? 'connected' : ''}`}></span>
          <span>{connected ? 'Connected' : 'Disconnected'}</span>
        </div>
      </header>

      <main className="main">
        <div className="tabs">
          <button
            className={`tab ${activeTab === 'overview' ? 'active' : ''}`}
            onClick={() => setActiveTab('overview')}
          >
            Overview
          </button>
          <button
            className={`tab ${activeTab === 'positions' ? 'active' : ''}`}
            onClick={() => setActiveTab('positions')}
          >
            Positions
            {status && status.active_position_sets > 0 && (
              <span style={{ marginLeft: '8px', opacity: 0.7 }}>
                ({status.active_position_sets})
              </span>
            )}
          </button>
          <button
            className={`tab ${activeTab === 'config' ? 'active' : ''}`}
            onClick={() => setActiveTab('config')}
          >
            Config
          </button>
          <button
            className={`tab ${activeTab === 'logs' ? 'active' : ''}`}
            onClick={() => setActiveTab('logs')}
          >
            Logs
          </button>
        </div>

        <div className="tab-content">
          {activeTab === 'overview' && <Overview status={status} />}
          {activeTab === 'positions' && <Positions positions={positions} />}
          {activeTab === 'config' && <Config />}
          {activeTab === 'logs' && <Logs />}
        </div>
      </main>
    </div>
  );
}

export default App;
