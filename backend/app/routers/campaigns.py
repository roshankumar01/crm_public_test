from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Lead, LeadActivity, Learner, MarketingCampaign, UploadBatch, User
from app.services.auth import get_current_user, require_admin
from app.services.importers.common import clean, clean_learner_number, dataframe_row_to_dict, read_upload, require_columns, upload_chunks

router = APIRouter(prefix="/campaigns", tags=["Campaigns"])


@router.get("")
def campaign_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    activity_query = (
        select(LeadActivity, Lead, Learner, User)
        .join(Lead, LeadActivity.lead_id == Lead.id)
        .join(Learner, Lead.learner_number == Learner.learner_number)
        .outerjoin(User, LeadActivity.user_id == User.id)
        .where(LeadActivity.activity_type.in_(["EMAIL_CAMPAIGN", "WHATSAPP_CAMPAIGN"]))
    )
    if current_user.role != "ADMIN":
        activity_query = activity_query.where(Lead.assigned_to_user_id == current_user.id)
    activity_rows = db.execute(activity_query.order_by(LeadActivity.created_at.desc())).all()

    items = [{
        "id": f"activity-{activity.id}",
        "campaign_name": activity.campaign_name or "Campaign",
        "channel": "Email" if activity.activity_type == "EMAIL_CAMPAIGN" else "WhatsApp",
        "learner_number": lead.learner_number,
        "learner_name": learner.name,
        "sent_by": sender.display_name if sender else "System",
        "sent_at": activity.created_at,
        "notes": activity.notes,
    } for activity, lead, learner, sender in activity_rows]

    if current_user.role == "ADMIN":
        uploaded_rows = db.execute(
            select(MarketingCampaign, Learner, User)
            .join(Learner, MarketingCampaign.learner_number == Learner.learner_number)
            .outerjoin(User, MarketingCampaign.uploaded_by_user_id == User.id)
            .order_by(MarketingCampaign.created_at.desc())
        ).all()
        items.extend({
            "id": f"upload-{campaign.id}",
            "campaign_name": campaign.campaign_name,
            "channel": campaign.marketing_type,
            "marketing_type": campaign.marketing_type,
            "learner_number": campaign.learner_number,
            "learner_name": learner.name,
            "sent_by": sender.display_name if sender else "System",
            "sent_at": campaign.created_at,
            "notes": None,
        } for campaign, learner, sender in uploaded_rows)

    items.sort(key=lambda item: item["sent_at"], reverse=True)
    return {
        "total_sent": len(items),
        "email_sent": sum(item["channel"] == "Email" for item in items),
        "whatsapp_sent": sum(item["channel"] == "WhatsApp" for item in items),
        "learners_reached": len({item["learner_number"] for item in items}),
        "items": items,
    }


@router.post("/upload")
def upload_marketing_campaigns(
    file: Annotated[UploadFile, File()],
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
    progress=None,
):
    batch = UploadBatch(
        import_type="MARKETING_CAMPAIGN",
        filename=file.filename or "unknown",
        status="PROCESSING",
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)

    try:
        df = read_upload(file)
        batch.rows_total = len(df)
        require_columns(df, {"learnernumber", "marketingtype", "campaignname"}, "Marketing campaign")
        if progress:
            progress(rows_total=len(df))

        imported = 0
        skipped = 0
        skipped_rows = []
        learners_created = 0
        duplicates = 0
        existing_keys = set(db.execute(select(
            MarketingCampaign.learner_number, MarketingCampaign.marketing_type, MarketingCampaign.campaign_name
        )).all())
        known_learners = set(db.scalars(select(Learner.learner_number)).all())
        for processed, rows in upload_chunks(df):
            for row in rows:
                learner_number = clean_learner_number(row.get("learnernumber"))
                campaign_name = clean(row.get("campaignname"))
                marketing_type = clean(row.get("marketingtype"))
                if not learner_number or not marketing_type or not campaign_name:
                    skipped += 1
                    skipped_rows.append({"row_number": processed - len(rows) + rows.index(row) + 2, "reason": "Missing learner number, marketing type, or campaign name", **dataframe_row_to_dict(row)})
                    continue
                if learner_number not in known_learners:
                    db.add(Learner(learner_number=learner_number, name="Unknown"))
                    known_learners.add(learner_number)
                    learners_created += 1
                key = (learner_number, marketing_type, campaign_name)
                if key in existing_keys:
                    skipped += 1
                    duplicates += 1
                    skipped_rows.append({"row_number": processed - len(rows) + rows.index(row) + 2, "reason": "Duplicate campaign row", **dataframe_row_to_dict(row)})
                    continue
                existing_keys.add(key)
                db.add(MarketingCampaign(
                    learner_number=learner_number,
                    campaign_name=campaign_name,
                    marketing_type=marketing_type,
                    upload_batch_id=batch.id,
                    uploaded_by_user_id=admin_user.id,
                ))
                imported += 1
            db.flush()
            if progress:
                progress(processed=processed, rows_imported=imported, rows_skipped=skipped,
                         learners_created=learners_created, duplicates_skipped=duplicates)

        batch.rows_imported = imported
        batch.rows_skipped = skipped
        batch.status = "COMPLETED"
        db.commit()
        db.refresh(batch)
        return {
            "id": batch.id,
            "filename": batch.filename,
            "status": batch.status,
            "rows_total": batch.rows_total,
            "rows_imported": batch.rows_imported,
            "rows_skipped": batch.rows_skipped,
            "learners_created": learners_created,
            "duplicates_skipped": duplicates,
            "skipped_rows": skipped_rows,
        }
    except ValueError as exc:
        db.rollback()
        failed_batch = db.get(UploadBatch, batch.id)
        if failed_batch:
            failed_batch.status = "FAILED"
            failed_batch.error_message = str(exc)
            db.commit()
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        db.rollback()
        failed_batch = db.get(UploadBatch, batch.id)
        if failed_batch:
            failed_batch.status = "FAILED"
            failed_batch.error_message = str(exc)
            db.commit()
        raise HTTPException(status_code=500, detail=str(exc))
