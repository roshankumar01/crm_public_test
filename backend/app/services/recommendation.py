from app.services.course_rules import build_learner_opportunities


def get_recommendations(history_rows):
    opportunities = build_learner_opportunities(history_rows)
    recommendations = [
        {
            "code": item["target_code"],
            "name": item["target_name"],
            "reason": item["reason"],
            "priority": item["priority"],
        }
        for item in opportunities
    ]
    return sorted(recommendations, key=lambda item: (item["priority"], item["code"]))
