import type { RecordItem } from '../api/client';
import { ImagePreview } from './ImagePreview';

export function RecordDetail({ record }: { record: RecordItem | null }) {
  if (!record) {
    return (
      <section className="detail-card empty-state">
        <h2>Chọn một dòng để xem chi tiết</h2>
        <p>Dữ liệu đầy đủ, choices và ảnh sẽ hiển thị tại đây.</p>
      </section>
    );
  }

  return (
    <section className="detail-card">
      <div className="detail-header">
        <span className="record-id">#{record.id}</span>
        <span className="chip">{record.split_origin || 'unknown'}</span>
      </div>
      <h2>{record.question || 'Câu hỏi chỉ có ảnh'}</h2>
      <dl className="detail-list">
        <dt>Answer</dt>
        <dd>{record.answer || <span className="muted">Trống</span>}</dd>
        <dt>Right choice</dt>
        <dd>{record.right_choice || <span className="muted">Trống</span>}</dd>
        <dt>Choices</dt>
        <dd>
          {record.parsed_choices.length ? (
            <ul>{record.parsed_choices.map((choice) => <li key={choice}>{choice}</li>)}</ul>
          ) : (
            <span className="muted">Không có choices</span>
          )}
        </dd>
        <dt>Instruction</dt>
        <dd>{record.instruction || <span className="muted">Trống</span>}</dd>
        <dt>Images</dt>
        <dd><ImagePreview images={record.parsed_images} /></dd>
      </dl>
    </section>
  );
}
