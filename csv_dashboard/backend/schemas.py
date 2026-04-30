from typing import Literal

from pydantic import BaseModel, Field, field_validator


class RecordBase(BaseModel):
    question: str = ""
    answer: str = ""
    right_choice: str = ""
    choices: str = "[]"
    instruction: str = ""
    images_path: str = "[]"
    split_origin: str = "manual"

    @field_validator("question", "answer", "right_choice", "choices", "instruction", "images_path", "split_origin", mode="before")
    @classmethod
    def normalize_text(cls, value: object) -> str:
        if value is None:
            return ""
        return str(value)


class RecordCreate(RecordBase):
    question: str = Field(min_length=1)

    @field_validator("question")
    @classmethod
    def question_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question must not be blank")
        return value.strip()


class RecordUpdate(BaseModel):
    question: str | None = None
    answer: str | None = None
    right_choice: str | None = None
    choices: str | None = None
    instruction: str | None = None
    images_path: str | None = None
    split_origin: str | None = None

    @field_validator("question", "answer", "right_choice", "choices", "instruction", "images_path", "split_origin", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: object) -> str | None:
        if value is None:
            return None
        return str(value)


class RecordOut(RecordBase):
    id: int
    parsed_choices: list[str] = []
    parsed_images: list[str] = []


class PaginatedRecords(BaseModel):
    items: list[RecordOut]
    page: int
    page_size: int
    total: int
    total_pages: int


class DeleteResponse(BaseModel):
    deleted: bool
    id: int


class ImportResponse(BaseModel):
    added: int
    updated_existing: int
    skipped: int
    warnings: list[str]


class BucketCount(BaseModel):
    label: str
    count: int


class NumericBucketCount(BaseModel):
    value: int
    count: int


class DatasetOverview(BaseModel):
    total_records: int
    records_with_images: int
    records_without_images: int
    multiple_choice_records: int
    open_ended_records: int
    avg_question_length: float
    avg_answer_length: float
    by_split_origin: list[BucketCount]
    choice_count_distribution: list[NumericBucketCount]
    image_count_distribution: list[NumericBucketCount]


class MissingColumnCount(BaseModel):
    column: str
    missing: int


class DataQualityStats(BaseModel):
    missing_by_column: list[MissingColumnCount]
    duplicate_ids: int
    duplicate_questions: int
    invalid_ids: int
    invalid_choices: int
    invalid_images_path: int
    missing_image_files: int
    empty_question_rows: int
    empty_answer_rows: int
    quality_score: float


class QualityIssueRecord(BaseModel):
    id: int | None = None
    issue_type: str
    question: str = ""
    detail: str = ""


class QualityIssues(BaseModel):
    items: list[QualityIssueRecord]
    page: int
    page_size: int
    total: int
    total_pages: int


SortDirection = Literal["asc", "desc"]
