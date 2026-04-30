import { useEffect, useState } from 'react';
import { getHealth } from './api/client';
import { DataQualityCharts } from './components/DataQualityCharts';
import { DatasetOverviewCharts } from './components/DatasetOverviewCharts';
import { Layout } from './components/Layout';
import { RecordsTable } from './components/RecordsTable';

export default function App() {
  const [activeTab, setActiveTab] = useState('records');
  const [healthStatus, setHealthStatus] = useState('checking');

  useEffect(() => {
    getHealth()
      .then((health) => setHealthStatus(health.status === 'ok' && health.csv_exists ? 'ok' : 'missing data'))
      .catch(() => setHealthStatus('offline'));
  }, []);

  return (
    <Layout activeTab={activeTab} onTabChange={setActiveTab} healthStatus={healthStatus}>
      {activeTab === 'records' && <RecordsTable />}
      {activeTab === 'overview' && <DatasetOverviewCharts />}
      {activeTab === 'quality' && <DataQualityCharts />}
    </Layout>
  );
}
