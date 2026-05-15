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

  const tabs: Array<{ id: TabType; label: string; badge?: string | number | null }> = [
    { id: 'overview', label: 'Mission Control' },
    { id: 'positions', label: 'Entries', badge: status && status.active_position_sets > 0 ? status.active_position_sets : null },
    { id: 'config', label: 'Strategy Setup' },
    { id: 'logs', label: 'Execution Log' },
  ];

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-block">
          <div className="brand-mark">DL</div>
          <div>
            <div className="brand-kicker">Bybit Ladder Strategy</div>
            <h1>Daily Ladder Bot</h1>
          </div>
        </div>

        <div className="topbar-meta">
          <div className={`connection-pill ${connected ? 'online' : 'offline'}`}>
            <span className="status-dot"></span>
            {connected ? 'Realtime feed connected' : 'Realtime feed reconnecting'}
          </div>
          {status && (
            <div className="account-pill">
              {status.dry_run ? 'Dry run mode' : status.testnet ? 'Testnet execution' : 'Mainnet execution'}
            </div>
          )}
        </div>
      </header>

      <main className="workspace">
        <nav className="tabs tabs-modern">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              className={`tab ${activeTab === tab.id ? 'active' : ''}`}
              onClick={() => setActiveTab(tab.id)}
            >
              <span>{tab.label}</span>
              {tab.badge ? <span className="tab-badge">{tab.badge}</span> : null}
            </button>
          ))}
        </nav>

        <section className="tab-stage">
          {activeTab === 'overview' && <Overview status={status} />}
          {activeTab === 'positions' && <Positions positions={positions} />}
          {activeTab === 'config' && <Config />}
          {activeTab === 'logs' && <Logs />}
        </section>
      </main>
    </div>
  );
}

export default App;
