export type RecordItem = {
  id: number;
  question: string;
  answer: string;
  right_choice: string;
  choices: string;
  instruction: string;
  images_path: string;
  split_origin: string;
  parsed_choices: string[];
  parsed_images: string[];
};

export type RecordPayload = Omit<RecordItem, 'id' | 'parsed_choices' | 'parsed_images'>;

export type PaginatedRecords = {
  items: RecordItem[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
};

export type BucketCount = { label: string; count: number };
export type NumericBucketCount = { value: number; count: number };

export type DatasetOverview = {
  total_records: number;
  records_with_images: number;
  records_without_images: number;
  multiple_choice_records: number;
  open_ended_records: number;
  avg_question_length: number;
  avg_answer_length: number;
  by_split_origin: BucketCount[];
  choice_count_distribution: NumericBucketCount[];
  image_count_distribution: NumericBucketCount[];
};

export type DataQualityStats = {
  missing_by_column: { column: string; missing: number }[];
  duplicate_ids: number;
  duplicate_questions: number;
  invalid_ids: number;
  invalid_choices: number;
  invalid_images_path: number;
  missing_image_files: number;
  empty_question_rows: number;
  empty_answer_rows: number;
  quality_score: number;
};

export type ImportResponse = {
  added: number;
  updated_existing: number;
  skipped: number;
  warnings: string[];
};

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(options?.headers ?? {}) },
    ...options,
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed: ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export function imageUrl(imagePath: string): string {
  const filename = imagePath.replace(/\\/g, '/').split('/').pop();
  return `${API_BASE_URL}/images/${filename}`;
}

export function csvDownloadUrl(): string {
  return `${API_BASE_URL}/api/download/csv`;
}

export function exportZipUrl(): string {
  return `${API_BASE_URL}/api/export/zip`;
}

export async function importParquet(file: File, options: { splitOrigin: string; translate: boolean; fillMissing: boolean }) {
  const formData = new FormData();
  formData.set('file', file);
  formData.set('split_origin', options.splitOrigin);
  formData.set('translate', String(options.translate));
  formData.set('fill_missing', String(options.fillMissing));

  const response = await fetch(`${API_BASE_URL}/api/import/parquet`, { method: 'POST', body: formData });
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed: ${response.status}`);
  }
  return response.json() as Promise<ImportResponse>;
}

export async function getHealth() {
  return request<{ status: string; csv_exists: boolean; image_dir_exists: boolean }>('/api/health');
}

export async function getRecords(params: Record<string, string | number | boolean | undefined>) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== '') search.set(key, String(value));
  }
  return request<PaginatedRecords>(`/api/records?${search.toString()}`);
}

export async function createRecord(payload: RecordPayload) {
  return request<RecordItem>('/api/records', { method: 'POST', body: JSON.stringify(payload) });
}

export async function updateRecord(id: number, payload: Partial<RecordPayload>) {
  return request<RecordItem>(`/api/records/${id}`, { method: 'PUT', body: JSON.stringify(payload) });
}

export async function deleteRecord(id: number) {
  return request<{ deleted: boolean; id: number }>(`/api/records/${id}`, { method: 'DELETE' });
}

export async function getOverviewStats() {
  return request<DatasetOverview>('/api/stats/overview');
}

export async function getQualityStats() {
  return request<DataQualityStats>('/api/stats/quality');
}
