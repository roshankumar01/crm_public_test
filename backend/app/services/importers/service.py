from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Course, LearnerCourseRecord, UploadBatch
from app.services.importers.common import dataframe_row_to_dict, read_upload, save_record, upload_chunks
from app.services.importers.registry import get_importer
from app.services.lead_workflow import mark_opportunities_dirty


def import_course_file(db: Session, import_type: str, upload_file, progress=None):
    importer = get_importer(import_type)

    batch = UploadBatch(
        import_type=importer.import_type,
        filename=upload_file.filename or "unknown",
        status="PROCESSING",
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)

    try:
        df = read_upload(upload_file)
        batch.rows_total = len(df)
        importer.validate_columns(df)
        if progress:
            progress(rows_total=len(df))

        imported = 0
        skipped = 0
        skipped_rows = []
        course_cache = {course.code: course for course in db.scalars(select(Course))}
        known_hashes = set(db.scalars(select(LearnerCourseRecord.row_hash)))

        for processed, rows in upload_chunks(df):
            for row in rows:
                raw_data = dataframe_row_to_dict(row)
                normalized_records = importer.parse_row(row)
                if not normalized_records:
                    skipped += 1
                    skipped_rows.append({"row_number": len(skipped_rows) + 2, "reason": "Row could not be parsed", **raw_data})
                    continue

                for normalized in normalized_records:
                    if save_record(db, normalized, raw_data, batch.id, course_cache, known_hashes):
                        imported += 1
                    else:
                        skipped += 1
                        skipped_rows.append({"row_number": len(skipped_rows) + 2, "reason": "Duplicate or invalid record", **raw_data})
            db.flush()
            if progress:
                progress(processed=processed, rows_imported=imported, rows_skipped=skipped)

        batch.rows_imported = imported
        batch.rows_skipped = skipped
        batch.status = "COMPLETED"
        if imported:
            mark_opportunities_dirty(db)
        db.commit()
        db.refresh(batch)
        batch.skipped_rows = skipped_rows
        return batch

    except Exception as exc:
        db.rollback()
        failed_batch = db.get(UploadBatch, batch.id)
        if failed_batch:
            failed_batch.status = "FAILED"
            failed_batch.error_message = str(exc)
            db.commit()
        raise
