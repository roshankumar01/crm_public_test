from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AppSetting, User
from app.services.auth import require_admin
from app.services.course_rules import COOLING_DAYS_KEY, get_cooling_days
from app.services.lead_workflow import mark_opportunities_dirty

router = APIRouter(prefix="/settings/recommendation-rules", tags=["Recommendation Rules"])


class CoolingDaysUpdate(BaseModel):
    cooling_days: int = Field(ge=0, le=3650)


@router.get("")
def get_rules(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return {
        "cooling_days": get_cooling_days(db),
        "stage_one": ["Advanced Diploma", "PG - Diploma", "Diploma", "National General Certificate", "IOSH MS", "Nebosh HSW"],
        "stage_two": ["IGC", "Nebosh PSM", "Nebosh Incident Investigation"],
        "stage_three": ["Nebosh PSM", "Nebosh Incident Investigation", "Nebosh Idip"],
        "idip_rule": "After passing any IDIP unit, recommend the remaining units not yet enrolled.",
    }


@router.patch("")
def update_rules(payload: CoolingDaysUpdate, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    setting = db.get(AppSetting, COOLING_DAYS_KEY)
    if setting:
        setting.value = str(payload.cooling_days)
    else:
        db.add(AppSetting(key=COOLING_DAYS_KEY, value=str(payload.cooling_days)))
    mark_opportunities_dirty(db)
    db.commit()
    return get_rules(admin, db)
