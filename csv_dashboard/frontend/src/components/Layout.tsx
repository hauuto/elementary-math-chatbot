type LayoutProps = {
  activeTab: string;
  onTabChange: (tab: string) => void;
  healthStatus: string;
  children: React.ReactNode;
};

const tabs = [
  { id: 'records', label: 'Records' },
  { id: 'overview', label: 'Overview' },
  { id: 'quality', label: 'Data Quality' },
];

export function Layout({ activeTab, onTabChange, healthStatus, children }: LayoutProps) {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">∑</span>
          <div>
            <strong>Math Warehouse</strong>
            <small>CSV data console</small>
          </div>
        </div>
        <nav className="nav-tabs" aria-label="Main navigation">
          {tabs.map((tab) => (
            <button key={tab.id} className={activeTab === tab.id ? 'active' : ''} onClick={() => onTabChange(tab.id)}>
              {tab.label}
            </button>
          ))}
        </nav>
      </aside>
      <main className="main-panel">
        <header className="topbar">
          <div>
            <p className="eyebrow">Elementary math dataset</p>
            <h1>Quản lý dữ liệu bài toán</h1>
          </div>
          <div className={`status-pill ${healthStatus === 'ok' ? 'online' : 'offline'}`}>
            Backend: {healthStatus}
          </div>
        </header>
        {children}
      </main>
    </div>
  );
}
