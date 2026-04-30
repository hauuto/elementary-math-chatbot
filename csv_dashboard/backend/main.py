from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .analytics import get_overview, get_quality_issues, get_quality_stats
from .config import CSV_PATH, IMAGE_DIR
from .csv_store import create_record, delete_record, get_record, query_records, update_record
from .importer import import_parquet_file
from .schemas import DeleteResponse, ImportResponse, RecordCreate, RecordUpdate

app = FastAPI(title="Elementary Math Data Warehouse API")

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://.*:5173",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if IMAGE_DIR.exists():
    app.mount("/images", StaticFiles(directory=IMAGE_DIR), name="images")


@app.get("/api/health")
def health() -> dict[str, bool | str]:
    return {
        "status": "ok",
        "csv_exists": CSV_PATH.exists(),
        "image_dir_exists": IMAGE_DIR.exists(),
    }


@app.get("/api/download/csv")
def download_csv():
    if not CSV_PATH.exists():
        raise HTTPException(status_code=404, detail="CSV file not found")
    return FileResponse(CSV_PATH, media_type="text/csv", filename=CSV_PATH.name)


@app.get("/api/export/zip")
def export_zip():
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        if CSV_PATH.exists():
            archive.write(CSV_PATH, CSV_PATH.name)
        if IMAGE_DIR.exists():
            for image_path in IMAGE_DIR.rglob("*"):
                if image_path.is_file():
                    archive.write(image_path, image_path.relative_to(IMAGE_DIR.parent).as_posix())
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="math_dataset_export.zip"'},
    )


@app.post("/api/import/parquet", response_model=ImportResponse)
async def import_parquet(
    file: UploadFile = File(...),
    split_origin: str = Form("parquet_upload"),
    translate: bool = Form(True),
    fill_missing: bool = Form(False),
):
    if not file.filename or not file.filename.lower().endswith(".parquet"):
        raise HTTPException(status_code=400, detail="Vui lòng tải lên file .parquet")
    try:
        return import_parquet_file(await file.read(), file.filename, split_origin, translate, fill_missing)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/records")
def list_records(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    search: str | None = None,
    split_origin: str | None = None,
    has_image: bool | None = None,
    missing_answer: bool | None = None,
    sort_by: str = "id",
    sort_dir: str = Query("asc", pattern="^(asc|desc)$"),
):
    return query_records(
        page=page,
        page_size=page_size,
        search=search,
        split_origin=split_origin,
        has_image=has_image,
        missing_answer=missing_answer,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )


@app.get("/api/records/{record_id}")
def read_record(record_id: int):
    record = get_record(record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Record not found")
    return record


@app.post("/api/records", status_code=201)
def create_record_endpoint(payload: RecordCreate):
    return create_record(payload)


@app.put("/api/records/{record_id}")
def update_record_endpoint(record_id: int, payload: RecordUpdate):
    record = update_record(record_id, payload)
    if record is None:
        raise HTTPException(status_code=404, detail="Record not found")
    return record


@app.delete("/api/records/{record_id}")
def delete_record_endpoint(record_id: int) -> DeleteResponse:
    deleted = delete_record(record_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Record not found")
    return DeleteResponse(deleted=True, id=record_id)


@app.get("/api/stats/overview")
def overview_stats():
    return get_overview()


@app.get("/api/stats/quality")
def quality_stats():
    return get_quality_stats()


@app.get("/api/stats/quality/issues")
def quality_issues(issue_type: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=200)):
    return get_quality_issues(issue_type=issue_type, page=page, page_size=page_size)
