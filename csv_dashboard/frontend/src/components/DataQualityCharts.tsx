import { useEffect, useState } from 'react';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { DataQualityStats, getQualityStats } from '../api/client';

export function DataQualityCharts() {
  const [stats, setStats] = useState<DataQualityStats | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    getQualityStats().then(setStats).catch((err) => setError(err instanceof Error ? err.message : 'Không tải được quality stats'));
  }, []);

  if (error) return <p className="form-error">{error}</p>;
  if (!stats) return <section className="dashboard-card">Đang tải quality dashboard...</section>;

  const issueCounts = [
    { label: 'Duplicate ID', count: stats.duplicate_ids },
    { label: 'Duplicate question', count: stats.duplicate_questions },
    { label: 'Invalid ID', count: stats.invalid_ids },
    { label: 'Invalid choices', count: stats.invalid_choices },
    { label: 'Invalid images', count: stats.invalid_images_path },
    { label: 'Missing image files', count: stats.missing_image_files },
    { label: 'Empty question', count: stats.empty_question_rows },
    { label: 'Empty answer', count: stats.empty_answer_rows },
  ];

  return (
    <div className="dashboard-grid">
      <section className="dashboard-card metric-card quality-score">
        <span>Quality score</span>
        <strong>{stats.quality_score}%</strong>
      </section>
      <MetricCard label="Duplicate questions" value={stats.duplicate_questions.toLocaleString()} />
      <MetricCard label="Missing answers" value={stats.empty_answer_rows.toLocaleString()} />
      <MetricCard label="Missing images" value={stats.missing_image_files.toLocaleString()} />

      <section className="dashboard-card chart-card wide">
        <h2>Missing values theo cột</h2>
        <ResponsiveContainer width="100%" height={310}>
          <BarChart data={stats.missing_by_column}>
            <CartesianGrid strokeDasharray="3 3" stroke="#263044" />
            <XAxis dataKey="column" tick={{ fill: '#94a3b8' }} />
            <YAxis tick={{ fill: '#94a3b8' }} />
            <Tooltip />
            <Bar dataKey="missing" fill="#f97316" radius={[8, 8, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </section>

      <section className="dashboard-card chart-card wide">
        <h2>Issue counts</h2>
        <ResponsiveContainer width="100%" height={310}>
          <BarChart data={issueCounts}>
            <CartesianGrid strokeDasharray="3 3" stroke="#263044" />
            <XAxis dataKey="label" tick={{ fill: '#94a3b8', fontSize: 11 }} interval={0} angle={-18} textAnchor="end" height={90} />
            <YAxis tick={{ fill: '#94a3b8' }} />
            <Tooltip />
            <Bar dataKey="count" fill="#f43f5e" radius={[8, 8, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </section>
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
