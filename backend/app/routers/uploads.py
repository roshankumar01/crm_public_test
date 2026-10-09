from io import BytesIO, StringIO
import csv
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db
from app.models import (
    DailyLearnerRow, Lead, LeadActivity, Learner, LearnerCourseRecord, LearnersCrmEnrollment,
    LearnersCrmProfile, MainCrmActivity, MainCrmLead, MarketingCampaign, UploadBatch, UpsellCourseCase, User,
)
from app.services.auth import require_admin
from app.services.importers import import_course_file, list_importers
from app.services.lead_workflow import mark_opportunities_dirty, sync_opportunity_leads
from app.services.upload_jobs import create_job, get_job, update_job

router = APIRouter(prefix="/uploads", tags=["Uploads"])


def run_upload_job(job_id, payload, filename, kind, import_type, source_category, mode, unique_number, admin_id):
    from app.routers import campaigns, learners_crm, main_crm

    with SessionLocal() as db:
        try:
            admin = db.get(User, admin_id)
            upload_file = UploadFile(file=BytesIO(payload), filename=filename)
            progress = lambda **values: update_job(job_id, **values)
            if kind == "MAIN_CRM":
                result = main_crm.upload_leads(source_category, upload_file, mode, unique_number, admin, db, progress)
            elif kind == "LEARNERS_CRM":
                result = learners_crm.upload(upload_file, mode, unique_number, admin, db, progress)
            elif kind == "LEARNERS_DAILY":
                result = learners_crm.upload_daily(upload_file, admin, db, progress)
            elif kind == "COURSE":
                batch = import_course_file(db, import_type, upload_file, progress)
                result = {"id": batch.id, "rows_total": batch.rows_total,
                          "rows_imported": batch.rows_imported, "rows_skipped": batch.rows_skipped}
                result["skipped_rows"] = getattr(batch, "skipped_rows", [])
            else:
                result = campaigns.upload_marketing_campaigns(upload_file, admin, db, progress)
            update_job(job_id, status="COMPLETED", processed=result["rows_total"],
                       rows_total=result["rows_total"], rows_imported=result["rows_imported"],
                       rows_skipped=result["rows_skipped"], result=result)
        except Exception as exc:
            db.rollback()
            detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
            update_job(job_id, status="FAILED", error_message=str(detail))


@router.post("/jobs")
def start_upload_job(
    background_tasks: BackgroundTasks,
    file: Annotated[UploadFile, File()],
    kind: Annotated[str, Form()],
    import_type: Annotated[str | None, Form()] = None,
    source_category: Annotated[str | None, Form()] = None,
    upload_mode: Annotated[str, Form()] = "CREATE",
    unique_number: Annotated[str | None, Form()] = None,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    from app.routers.main_crm import SOURCE_CATEGORIES
    from app.services.importers.registry import get_importer

    kind = kind.strip().upper()
    mode = upload_mode.strip().upper()
    if kind not in {"MAIN_CRM", "LEARNERS_CRM", "LEARNERS_DAILY", "COURSE", "CAMPAIGN"}:
        raise HTTPException(status_code=400, detail="Invalid upload kind.")
    if not (file.filename or "").lower().endswith((".xlsx", ".csv")):
        raise HTTPException(status_code=400, detail="Only .xlsx and .csv files are supported.")
    if kind == "MAIN_CRM":
        if source_category not in SOURCE_CATEGORIES:
            raise HTTPException(status_code=400, detail="Invalid lead source category.")
        if mode not in {"CREATE", "UPDATE"}:
            raise HTTPException(status_code=400, detail="Invalid upload mode.")
        if mode == "UPDATE" and not db.scalar(select(UploadBatch.id).where(
            UploadBatch.unique_number == unique_number,
            UploadBatch.import_type.like("MAIN_CRM_%"),
            UploadBatch.import_type != "MAIN_CRM_MIGRATION",
        )):
            raise HTTPException(status_code=404, detail="Upload number not found.")
    elif kind == "LEARNERS_CRM":
        if mode not in {"CREATE", "UPDATE"}:
            raise HTTPException(status_code=400, detail="Invalid upload mode.")
        if mode == "UPDATE" and not db.scalar(select(UploadBatch.id).where(
            UploadBatch.unique_number == unique_number, UploadBatch.import_type == "LEARNERS_CRM"
        )):
            raise HTTPException(status_code=404, detail="Learner upload number not found.")
    elif kind == "COURSE":
        try:
            get_importer(import_type or "")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    update_target = unique_number if mode == "UPDATE" and kind in {"MAIN_CRM", "LEARNERS_CRM"} else None
    job_id = create_job(kind, file.filename or "unknown", update_target)
    background_tasks.add_task(run_upload_job, job_id, file.file.read(), file.filename or "unknown",
                              kind, import_type, source_category, mode, unique_number, admin_user.id)
    return {"job_id": job_id, "status": "PROCESSING"}


@router.get("/jobs/{job_id}")
def upload_job_progress(job_id: str, admin_user: User = Depends(require_admin)):
    return get_job(job_id)


@router.get("/jobs/{job_id}/skipped")
def download_skipped_rows(job_id: str, admin_user: User = Depends(require_admin)):
    job = get_job(job_id)
    rows = (job.get("result") or {}).get("skipped_rows") or []
    output = StringIO(newline="")
    if rows:
        keys = []
        for row in rows:
            for key in row:
                if key not in keys:
                    keys.append(key)
        writer = csv.DictWriter(output, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    else:
        output.write("row_number,reason\n")
    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="skipped-rows-{job_id}.csv"'})


class ResetUploadsRequest(BaseModel):
    upload_ids: list[int]
    confirmation: str


class ResetAllDataRequest(BaseModel):
    confirmation: str


@router.post("/reset-all")
def reset_all_data(payload: ResetAllDataRequest, admin_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    if admin_user.role != "ADMIN": raise HTTPException(403, "Admin access required.")
    if payload.confirmation != "RESET ALL CRM DATA": raise HTTPException(400, "Type RESET ALL CRM DATA to confirm.")
    from app.services.upload_jobs import has_processing_jobs
    if has_processing_jobs(): raise HTTPException(409, "An upload is still processing. Wait for it to finish before resetting data.")
    from app.services.data_reset import clear_crm_data
    try:
        counts = clear_crm_data(db)
        db.commit()
        sync_opportunity_leads(db)
    except Exception:
        db.rollback()
        raise
    return {"rows_deleted": counts, "uploads_deleted": counts["upload_batches"], "all_data_reset": True}


@router.get("/reset-options")
def reset_options(admin_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    batches = db.execute(select(UploadBatch).order_by(UploadBatch.uploaded_at.desc(), UploadBatch.id.desc())).scalars().all()
    return [{
        "id": batch.id, "filename": batch.filename, "import_type": batch.import_type,
        "unique_number": batch.unique_number, "rows_imported": batch.rows_imported,
        "uploaded_at": batch.uploaded_at,
    } for batch in batches]


@router.post("/reset")
def reset_selected_uploads(
    payload: ResetUploadsRequest,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    ids = set(payload.upload_ids)
    if not ids or len(ids) != len(payload.upload_ids) or any(item <= 0 for item in ids):
        raise HTTPException(status_code=400, detail="Select one or more valid upload files.")
    if payload.confirmation != "DELETE SELECTED UPLOADS":
        raise HTTPException(status_code=400, detail="Type DELETE SELECTED UPLOADS to confirm.")
    batches = db.execute(select(UploadBatch).where(UploadBatch.id.in_(ids))).scalars().all()
    if len(batches) != len(ids):
        raise HTTPException(status_code=404, detail="One or more selected uploads no longer exist. Refresh and try again.")

    try:
        # Remove only records with explicit provenance to a selected upload.
        affected_learner_numbers = set(db.execute(select(LearnerCourseRecord.learner_number).where(
            LearnerCourseRecord.upload_batch_id.in_(ids)
        )).scalars().all())
        affected_learner_numbers.update(db.execute(select(MarketingCampaign.learner_number).where(
            MarketingCampaign.upload_batch_id.in_(ids)
        )).scalars().all())
        affected_profile_ids = set(db.execute(select(LearnersCrmEnrollment.learner_id).where(
            LearnersCrmEnrollment.upload_batch_id.in_(ids)
        )).scalars().all())
        db.execute(delete(MainCrmActivity).where(MainCrmActivity.upload_batch_id.in_(ids)))
        db.execute(delete(LearnerCourseRecord).where(LearnerCourseRecord.upload_batch_id.in_(ids)))
        db.execute(delete(MarketingCampaign).where(MarketingCampaign.upload_batch_id.in_(ids)))
        db.execute(delete(LearnersCrmEnrollment).where(LearnersCrmEnrollment.upload_batch_id.in_(ids)))
        db.execute(delete(DailyLearnerRow).where(DailyLearnerRow.upload_batch_id.in_(ids)))

        # A shared lead may still have activity from another upload. Preserve it.
        has_activity = select(MainCrmActivity.id).where(MainCrmActivity.lead_id == MainCrmLead.id).exists()
        db.execute(delete(MainCrmLead).where(MainCrmLead.upload_batch_id.in_(ids), ~has_activity))
        db.execute(update(MainCrmLead).where(MainCrmLead.upload_batch_id.in_(ids)).values(upload_batch_id=None))

        # Only profiles touched by selected files are eligible for orphan cleanup.
        has_enrolment = select(LearnersCrmEnrollment.enrolment_id).where(
            LearnersCrmEnrollment.learner_id == LearnersCrmProfile.id
        ).exists()
        if affected_profile_ids:
            db.execute(delete(LearnersCrmProfile).where(LearnersCrmProfile.id.in_(affected_profile_ids), ~has_enrolment))

        # An Upsell learner is removed only when no other import or manually
        # maintained lead history still refers to that learner.
        for learner_number in affected_learner_numbers:
            has_course = db.scalar(select(LearnerCourseRecord.id).where(LearnerCourseRecord.learner_number == learner_number).limit(1))
            has_campaign = db.scalar(select(MarketingCampaign.id).where(MarketingCampaign.learner_number == learner_number).limit(1))
            has_main_crm_link = db.scalar(select(MainCrmLead.id).where(MainCrmLead.matched_learner_number == learner_number).limit(1))
            lead_ids = select(Lead.id).where(Lead.learner_number == learner_number)
            has_manual_history = db.scalar(select(LeadActivity.id).where(LeadActivity.lead_id.in_(lead_ids)).limit(1))
            has_manual_history = has_manual_history or db.scalar(select(UpsellCourseCase.id).where(UpsellCourseCase.lead_id.in_(lead_ids)).limit(1))
            if not (has_course or has_campaign or has_main_crm_link or has_manual_history):
                db.execute(delete(Lead).where(Lead.learner_number == learner_number))
                db.execute(delete(Learner).where(Learner.learner_number == learner_number))

        db.execute(delete(UploadBatch).where(UploadBatch.id.in_(ids)))
        # Any upload can affect registration state or the source contact set;
        # invalidate and immediately reconcile generated Upsell opportunities.
        mark_opportunities_dirty(db)
        db.commit()
        sync_opportunity_leads(db)
    except Exception:
        db.rollback()
        raise
    return {"uploads_deleted": len(ids)}


@router.get("/import-types")
def get_import_types(admin_user: User = Depends(require_admin)):
    return [
        {
            "import_type": item.import_type,
            "display_name": item.display_name,
            "description": item.description,
            "columns": item.columns,
        }
        for item in list_importers()
    ]


@router.get("")
def get_uploads(
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return db.execute(
        select(UploadBatch).order_by(UploadBatch.uploaded_at.desc()).limit(50)
    ).scalars().all()


@router.post("")
def upload_excel(
    import_type: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        batch = import_course_file(db, import_type, file)
        return {
            "id": batch.id,
            "filename": batch.filename,
            "import_type": batch.import_type,
            "status": batch.status,
            "rows_total": batch.rows_total,
            "rows_imported": batch.rows_imported,
            "rows_skipped": batch.rows_skipped,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
