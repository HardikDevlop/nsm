from datetime import datetime

from sqlalchemy.orm import Session

from backend.models import KnowledgeArticle, KnowledgeArticleHistory


ALLOWED_TRANSITIONS = {
    "draft": {"review"},
    "review": {"draft", "published"},
    "published": {"retired"},
    "retired": {"draft"},
}


class KnowledgeTransitionError(ValueError):
    pass


def transition_article(db: Session, article: KnowledgeArticle, target: str, actor_id: int) -> None:
    allowed = ALLOWED_TRANSITIONS.get(article.status, set())
    if target not in allowed:
        raise KnowledgeTransitionError(f"Invalid knowledge article transition: {article.status} -> {target}")
    now = datetime.utcnow()
    previous = article.status
    article.status = target
    article.updated_by = actor_id
    article.updated_at = now
    if target == "published":
        article.published_at = now
    action = {
        ("draft", "review"): "submitted_for_review",
        ("review", "draft"): "returned_to_draft",
        ("review", "published"): "published",
        ("published", "retired"): "retired",
        ("retired", "draft"): "restored",
    }[(previous, target)]
    db.add(KnowledgeArticleHistory(article_id=article.id, action=action, actor_id=actor_id, metadata_json={"from": previous, "to": target}, created_at=now))
