from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Lead, User
from app.services.lead_workflow import sync_opportunity_leads
from app.services.date_filters import period_condition
from app.services.upsell_management import work_items

SECTION_CONFIG = {
    "IGC": ("IGC", "Stage 2 · IGC"),
    "PSM_2": ("Nebosh PSM", "Stage 2 · Process Safety Management"),
    "INCIDENT_2": ("Nebosh Incident Investigation", "Stage 2 · Incident Investigation"),
    "PSM_3": ("Nebosh PSM", "Stage 3 · Process Safety Management"),
    "INCIDENT_3": ("Nebosh Incident Investigation", "Stage 3 · Incident Investigation"),
    "IDP_ENTRY": ("Nebosh Idip", "Stage 3 · IDIP entry"),
    "ID1": ("IDIP -1", "Stage 3 · IDIP 1"),
    "ID2": ("IDIP -2", "Stage 3 · IDIP 2"),
    "ID3": ("IDIP -3", "Stage 3 · IDIP 3"),
}
SECTION_ORDER = tuple(SECTION_CONFIG)


def section_key(opportunity_key: str, stage: int | None) -> str:
    if opportunity_key in {"PSM", "INCIDENT"}:
        return f"{opportunity_key}_{stage or 2}"
    return opportunity_key


def section_filter(key: str):
    if key in {"PSM_2", "PSM_3", "INCIDENT_2", "INCIDENT_3"}:
        name, stage = key.rsplit("_", 1)
        return (Lead.opportunity_key == name, Lead.stage == int(stage))
    if key in SECTION_CONFIG:
        return (Lead.opportunity_key == key,)
    return None


def get_all_opportunities(db: Session, current_user: User | None = None, period: str = "all"):
    """Small grouped summary; lead rows are fetched from the paged /leads API."""
    sync_opportunity_leads(db)
    filters = [Lead.is_active.is_(True)]
    filters.extend(period_condition(Lead.created_at, period))
    if current_user and current_user.role != "ADMIN":
        filters.append(Lead.assigned_to_user_id == current_user.id)
    rows = db.execute(select(
        Lead.opportunity_key, Lead.stage, Lead.status, Lead.assigned_to_user_id, func.count(Lead.id)
    ).where(*filters).group_by(
        Lead.opportunity_key, Lead.stage, Lead.status, Lead.assigned_to_user_id
    )).all()
    counts = {key: 0 for key in SECTION_ORDER}
    statuses = {"NEW": 0, "IN_CONTACT": 0, "CONVERTED": 0, "REJECTED": 0}
    total = unassigned = 0
    for key, stage, status, owner, count in rows:
        label = section_key(key, stage)
        counts[label] = counts.get(label, 0) + count
        statuses[status] = statuses.get(status, 0) + count
        total += count
        if owner is None:
            unassigned += count
    W = work_items().c
    work_scope = period_condition(W.created_at, period)
    if current_user and current_user.role != "ADMIN": work_scope.append(W.assigned_to_user_id == current_user.id)
    statuses = dict(db.execute(select(W.status, func.count()).where(*work_scope).group_by(W.status)).all())
    unique_learners = db.scalar(select(func.count(func.distinct(Lead.customer_id))).where(*filters)) or 0
    return {
        "summary": {
            "unique_learners": unique_learners,
            "total_opportunities": total,
            "idp_entry": counts["IDP_ENTRY"], "id1": counts["ID1"],
            "id2": counts["ID2"], "id3": counts["ID3"],
            "new": statuses.get("NEW", 0), "in_contact": statuses.get("IN_CONTACT", 0),
            "converted": statuses.get("CONVERTED", 0), "rejected": statuses.get("REJECTED", 0),
            "unassigned": unassigned,
            "by_target": [{"key": key, "name": SECTION_CONFIG[key][1], "count": counts[key]} for key in SECTION_ORDER],
        },
        "sections": [{"key": key, "title": SECTION_CONFIG[key][1],
                      "target_code": SECTION_CONFIG[key][0],
                      "description": f"Current recommendation for {SECTION_CONFIG[key][0]}.",
                      "count": counts[key]} for key in SECTION_ORDER],
    }
