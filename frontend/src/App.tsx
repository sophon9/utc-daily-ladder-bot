import { useEffect, useState } from 'react';
import { useWebSocket } from './hooks/useBot';
import Overview from './components/Overview';
import Positions from './components/Positions';
import Config from './components/Config';
import Logs from './components/Logs';
import './styles/app.css';

type TabType = 'overview' | 'positions' | 'config' | 'logs';
type ThemeType = 'light' | 'dark';

const THEME_STORAGE_KEY = 'advantage-price-theme';

function getInitialTheme(): ThemeType {
  const storedTheme = window.localStorage.getItem(THEME_STORAGE_KEY);
  if (storedTheme === 'light' || storedTheme === 'dark') {
    return storedTheme;
  }
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function App() {
  const { status, positions, connected } = useWebSocket();
  const [activeTab, setActiveTab] = useState<TabType>('overview');
  const [theme, setTheme] = useState<ThemeType>(getInitialTheme);
  const botName = status?.bot_name?.trim() || 'Advantage Price Bot';
  const accountName = status?.account_name?.trim() || 'Primary Account';
  const nextTheme = theme === 'dark' ? 'light' : 'dark';

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  }, [theme]);

  const tabs: Array<{ id: TabType; label: string; badge?: string | number | null }> = [
    { id: 'overview', label: 'Overview' },
    { id: 'positions', label: 'Positions', badge: status && status.active_position_sets > 0 ? status.active_position_sets : null },
    { id: 'config', label: 'Settings' },
    { id: 'logs', label: 'Logs' },
  ];

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-block">
          <div className="brand-mark">AP</div>
          <div>
            <div className="brand-kicker">{accountName}</div>
            <h1>{botName}</h1>
          </div>
        </div>

        <div className="topbar-meta">
          <button
            className="theme-toggle"
            type="button"
            onClick={() => setTheme(nextTheme)}
            aria-label={`Switch to ${nextTheme} theme`}
          >
            <span className="theme-toggle-icon">{theme === 'dark' ? 'D' : 'L'}</span>
            {theme === 'dark' ? 'Dark' : 'Light'}
          </button>
          <div className={`connection-pill ${connected ? 'online' : 'offline'}`}>
            <span className="status-dot"></span>
            {connected ? 'Live data connected' : 'Reconnecting'}
          </div>
          {status && (
            <div className="account-pill">
              {status.dry_run ? 'Simulation' : status.testnet ? 'Testnet' : 'Mainnet'}
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
