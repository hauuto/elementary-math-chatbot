import { useEffect, useState } from 'react';
import type { RecordItem, RecordPayload } from '../api/client';

const emptyPayload: RecordPayload = {
  question: '',
  answer: '',
  right_choice: '',
  choices: '[]',
  instruction: '',
  images_path: '[]',
  split_origin: 'manual',
};

export function RecordForm({
  record,
  onSubmit,
  onCancel,
}: {
  record: RecordItem | null;
  onSubmit: (payload: RecordPayload) => Promise<void>;
  onCancel: () => void;
}) {
  const [payload, setPayload] = useState<RecordPayload>(emptyPayload);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (record) {
      setPayload({
        question: record.question,
        answer: record.answer,
        right_choice: record.right_choice,
        choices: record.choices || '[]',
        instruction: record.instruction,
        images_path: record.images_path || '[]',
        split_origin: record.split_origin || 'manual',
      });
    } else {
      setPayload(emptyPayload);
    }
  }, [record]);

  function updateField(field: keyof RecordPayload, value: string) {
    setPayload((current) => ({ ...current, [field]: value }));
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError('');
    if (!payload.question.trim()) {
      setError('Question không được để trống khi tạo/sửa bằng form.');
      return;
    }

    setSaving(true);
    try {
      await onSubmit(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không lưu được dữ liệu');
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="record-form" onSubmit={handleSubmit}>
      <div className="form-header">
        <h2>{record ? `Sửa record #${record.id}` : 'Tạo record mới'}</h2>
        <button type="button" className="ghost-button" onClick={onCancel}>Đóng</button>
      </div>
      {error && <p className="form-error">{error}</p>}
      <label>
        Question
        <textarea value={payload.question} onChange={(event) => updateField('question', event.target.value)} rows={4} />
      </label>
      <label>
        Answer
        <textarea value={payload.answer} onChange={(event) => updateField('answer', event.target.value)} rows={5} />
      </label>
      <div className="form-grid">
        <label>
          Right choice
          <input value={payload.right_choice} onChange={(event) => updateField('right_choice', event.target.value)} />
        </label>
        <label>
          Split origin
          <input value={payload.split_origin} onChange={(event) => updateField('split_origin', event.target.value)} />
        </label>
      </div>
      <label>
        Choices
        <textarea value={payload.choices} onChange={(event) => updateField('choices', event.target.value)} rows={3} />
      </label>
      <label>
        Images path
        <textarea value={payload.images_path} onChange={(event) => updateField('images_path', event.target.value)} rows={3} />
      </label>
      <label>
        Instruction
        <textarea value={payload.instruction} onChange={(event) => updateField('instruction', event.target.value)} rows={3} />
      </label>
      <button className="primary-button" type="submit" disabled={saving}>{saving ? 'Đang lưu...' : 'Lưu thay đổi'}</button>
    </form>
  );
}
