from datetime import date, datetime, time, timedelta


PERIODS = ("today", "yesterday", "last_7_days", "last_month", "all")


def period_bounds(period: str | None):
    period = (period or "all").strip().lower()
    if period not in PERIODS:
        period = "all"
    if period == "all":
        return None
    today = date.today()
    if period == "today":
        start_day = end_day = today
    elif period == "yesterday":
        start_day = end_day = today - timedelta(days=1)
    elif period == "last_7_days":
        start_day, end_day = today - timedelta(days=6), today
    else:
        start_day, end_day = today - timedelta(days=29), today
    return datetime.combine(start_day, time.min), datetime.combine(end_day + timedelta(days=1), time.min)


def period_condition(column, period: str | None):
    bounds = period_bounds(period)
    if not bounds:
        return []
    start, end = bounds
    return [column >= start, column < end]
