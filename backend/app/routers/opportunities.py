from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.services.auth import get_current_user
from app.services.opportunities import get_all_opportunities

router = APIRouter(prefix="/opportunities", tags=["Opportunities"])


@router.get("")
def get_opportunities(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_all_opportunities(db, current_user)


@router.get("/idp")
def get_old_idp_opportunities(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    data = get_all_opportunities(db, current_user)
    section = next((section for section in data["sections"] if section["key"] == "IDP_ENTRY"), None)
    return {"count": section["count"] if section else 0, "section": "IDP_ENTRY"}
