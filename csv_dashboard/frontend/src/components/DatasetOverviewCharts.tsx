import { useEffect, useState } from 'react';
import { Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { DatasetOverview, getOverviewStats } from '../api/client';

const colors = ['#60a5fa', '#34d399', '#fbbf24', '#f472b6', '#a78bfa'];

export function DatasetOverviewCharts() {
  const [stats, setStats] = useState<DatasetOverview | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    getOverviewStats().then(setStats).catch((err) => setError(err instanceof Error ? err.message : 'Không tải được overview'));
  }, []);

  if (error) return <p className="form-error">{error}</p>;
  if (!stats) return <section className="dashboard-card">Đang tải dashboard...</section>;

  const imagePie = [
    { name: 'Có ảnh', value: stats.records_with_images },
    { name: 'Không ảnh', value: stats.records_without_images },
  ];

  return (
    <div className="dashboard-grid">
      <MetricCard label="Tổng records" value={stats.total_records.toLocaleString()} />
      <MetricCard label="Có ảnh" value={stats.records_with_images.toLocaleString()} />
      <MetricCard label="Trắc nghiệm" value={stats.multiple_choice_records.toLocaleString()} />
      <MetricCard label="Độ dài câu hỏi TB" value={String(stats.avg_question_length)} />

      <section className="dashboard-card chart-card">
        <h2>Tỷ lệ ảnh</h2>
        <ResponsiveContainer width="100%" height={260}>
          <PieChart>
            <Pie data={imagePie} dataKey="value" nameKey="name" outerRadius={92} label>
              {imagePie.map((_, index) => <Cell key={index} fill={colors[index % colors.length]} />)}
            </Pie>
            <Tooltip />
          </PieChart>
        </ResponsiveContainer>
      </section>

      <section className="dashboard-card chart-card wide">
        <h2>Top split_origin / domain</h2>
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={stats.by_split_origin.slice(0, 10)}>
            <CartesianGrid strokeDasharray="3 3" stroke="#263044" />
            <XAxis dataKey="label" tick={{ fill: '#94a3b8', fontSize: 11 }} interval={0} angle={-18} textAnchor="end" height={90} />
            <YAxis tick={{ fill: '#94a3b8' }} />
            <Tooltip />
            <Bar dataKey="count" fill="#60a5fa" radius={[8, 8, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </section>

      <Distribution title="Phân bố số choices" data={stats.choice_count_distribution} />
      <Distribution title="Phân bố số ảnh" data={stats.image_count_distribution} />
    </div>
  );
}

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <section className="dashboard-card metric-card">
      <span>{label}</span>
      <strong>{value}</strong>
    </section>
  );
}

function Distribution({ title, data }: { title: string; data: { value: number; count: number }[] }) {
  return (
    <section className="dashboard-card chart-card">
      <h2>{title}</h2>
      <ResponsiveContainer width="100%" height={250}>
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#263044" />
          <XAxis dataKey="value" tick={{ fill: '#94a3b8' }} />
          <YAxis tick={{ fill: '#94a3b8' }} />
          <Tooltip />
          <Bar dataKey="count" fill="#34d399" radius={[8, 8, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </section>
  );
}
