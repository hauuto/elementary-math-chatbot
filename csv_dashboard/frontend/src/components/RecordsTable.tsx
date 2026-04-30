import { useEffect, useState } from 'react';
import { createRecord, deleteRecord, getRecords, RecordItem, RecordPayload, updateRecord } from '../api/client';
import { RecordDetail } from './RecordDetail';
import { RecordForm } from './RecordForm';

export function RecordsTable() {
  const [records, setRecords] = useState<RecordItem[]>([]);
  const [selected, setSelected] = useState<RecordItem | null>(null);
  const [editing, setEditing] = useState<RecordItem | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [search, setSearch] = useState('');
  const [hasImage, setHasImage] = useState('');
  const [missingAnswer, setMissingAnswer] = useState('');
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function loadRecords() {
    setLoading(true);
    setError('');
    try {
      const data = await getRecords({
        page,
        page_size: 25,
        search,
        has_image: hasImage === '' ? undefined : hasImage === 'true',
        missing_answer: missingAnswer === '' ? undefined : missingAnswer === 'true',
      });
      setRecords(data.items);
      setTotalPages(data.total_pages);
      setTotal(data.total);
      setSelected((current) => data.items.find((item) => item.id === current?.id) ?? data.items[0] ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không tải được dữ liệu');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadRecords();
  }, [page, hasImage, missingAnswer]);

  async function submitCreate(payload: RecordPayload) {
    const created = await createRecord(payload);
    setShowCreate(false);
    setSelected(created);
    await loadRecords();
  }

  async function submitEdit(payload: RecordPayload) {
    if (!editing) return;
    const updated = await updateRecord(editing.id, payload);
    setEditing(null);
    setSelected(updated);
    await loadRecords();
  }

  async function removeRecord(record: RecordItem) {
    const confirmed = window.confirm(`Xóa record #${record.id}? Thao tác này sẽ ghi trực tiếp vào CSV.`);
    if (!confirmed) return;
    await deleteRecord(record.id);
    if (selected?.id === record.id) setSelected(null);
    await loadRecords();
  }

  return (
    <div className="records-layout">
      <section className="table-card">
        <div className="toolbar">
          <div>
            <h2>Records</h2>
            <p>{total.toLocaleString()} dòng dữ liệu</p>
          </div>
          <button className="primary-button" onClick={() => setShowCreate(true)}>Tạo record</button>
        </div>
        <div className="filters">
          <input
            placeholder="Tìm theo câu hỏi, answer, choices..."
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                setPage(1);
                loadRecords();
              }
            }}
          />
          <select value={hasImage} onChange={(event) => { setHasImage(event.target.value); setPage(1); }}>
            <option value="">Tất cả ảnh</option>
            <option value="true">Có ảnh</option>
            <option value="false">Không ảnh</option>
          </select>
          <select value={missingAnswer} onChange={(event) => { setMissingAnswer(event.target.value); setPage(1); }}>
            <option value="">Tất cả answer</option>
            <option value="true">Thiếu answer</option>
            <option value="false">Có answer</option>
          </select>
          <button className="secondary-button" onClick={() => { setPage(1); loadRecords(); }}>Tìm</button>
        </div>
        {error && <p className="form-error">{error}</p>}
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>Question</th>
                <th>Answer</th>
                <th>Images</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={5}>Đang tải...</td></tr>
              ) : records.map((record) => (
                <tr key={record.id} className={selected?.id === record.id ? 'selected' : ''} onClick={() => setSelected(record)}>
                  <td>#{record.id}</td>
                  <td className="truncate">{record.question || 'Câu hỏi chỉ có ảnh'}</td>
                  <td className="truncate">{record.answer || '—'}</td>
                  <td>{record.parsed_images.length}</td>
                  <td className="actions" onClick={(event) => event.stopPropagation()}>
                    <button onClick={() => setEditing(record)}>Sửa</button>
                    <button className="danger" onClick={() => removeRecord(record)}>Xóa</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="pagination">
          <button disabled={page <= 1} onClick={() => setPage((current) => current - 1)}>Trước</button>
          <span>Trang {page} / {totalPages}</span>
          <button disabled={page >= totalPages} onClick={() => setPage((current) => current + 1)}>Sau</button>
        </div>
      </section>
      <RecordDetail record={selected} />
      {(showCreate || editing) && (
        <div className="modal-backdrop">
          <RecordForm record={editing} onSubmit={editing ? submitEdit : submitCreate} onCancel={() => { setShowCreate(false); setEditing(null); }} />
        </div>
      )}
    </div>
  );
}
