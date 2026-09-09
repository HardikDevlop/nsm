from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.api.knowledge_routes import ArticleCreatePayload, ArticleUpdatePayload, FeedbackPayload, _validate_owner, get_article, link_change, link_ci, link_related, router, submit_feedback, unlink_change
from backend.knowledge.service import KnowledgeTransitionError, transition_article
from backend.models import ChangeRequest, CIType, ConfigurationItem, KnowledgeArticle, KnowledgeArticleHistory, KnowledgeChangeLink, KnowledgeCILink, KnowledgeFeedback, KnowledgeRelatedLink, Problem, User
from backend.database.session import Base


def test_article_supports_known_errors_and_typed_nms_links():
    payload = ArticleCreatePayload(title="BGP flap workaround", article_type="known_error", body="Reset peer", incident_ids=[1], problem_ids=[2], device_ids=[3], service_ids=[4])
    assert payload.article_type == "known_error"
    assert payload.service_ids == [4]


def test_article_update_supports_versioned_publish_lifecycle():
    assert ArticleUpdatePayload(title="Updated", body="New revision").title == "Updated"


def test_knowledge_routes_cover_search_versions_and_updates():
    paths = {route.path for route in router.routes}
    assert "/api/v1/knowledge" in paths
    assert "/api/v1/knowledge/{article_id}" in paths
    assert "/api/v1/knowledge/{article_id}/versions" in paths


def test_article_metadata_owner_lifecycle_and_history_persist():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    now = datetime.utcnow()
    active = User(id=41, name="Knowledge owner", email="kb-owner@example.com", password_hash="x", status="active")
    inactive = User(id=42, name="Inactive", email="kb-inactive@example.com", password_hash="x", status="inactive")
    article = KnowledgeArticle(number="KB-000041", title="Runbook", summary="Summary", article_type="runbook", category="network", tags=["bgp", "routing"], owner_id=41, status="draft", current_version=1, created_by=41, updated_by=41, created_at=now, updated_at=now)
    db.add_all([active, inactive, article]); db.flush()
    _validate_owner(db, 41)
    with pytest.raises(Exception, match="active user"):
        _validate_owner(db, 42)
    transition_article(db, article, "review", 41)
    transition_article(db, article, "published", 41)
    assert article.published_at is not None
    with pytest.raises(KnowledgeTransitionError):
        transition_article(db, article, "draft", 41)
    transition_article(db, article, "retired", 41)
    transition_article(db, article, "draft", 41)
    db.commit()
    assert article.tags == ["bgp", "routing"]
    assert [row.action for row in db.query(KnowledgeArticleHistory).order_by(KnowledgeArticleHistory.id)] == ["submitted_for_review", "published", "retired", "restored"]


def test_change_ci_related_and_feedback_relationships_are_persisted_safely():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    now = datetime.utcnow()
    user = User(id=51, name="Reader", email="reader@example.com", password_hash="x", status="active")
    change = ChangeRequest(id=61, number="CHG-000061", title="Change", category="normal", risk="low", impact="low", status="draft", created_at=now, updated_at=now)
    ci_type = CIType(id=71, name="Network CI", category="network", created_at=now, updated_at=now)
    ci = ConfigurationItem(id=72, ci_type_id=71, name="Core CI", lifecycle_state="operational", created_at=now, updated_at=now)
    article = KnowledgeArticle(id=81, number="KB-000081", title="Article", article_type="knowledge", status="draft", current_version=1, tags=[], created_at=now, updated_at=now)
    related = KnowledgeArticle(id=82, number="KB-000082", title="Related", article_type="knowledge", status="draft", current_version=1, tags=[], created_at=now, updated_at=now)
    db.add_all([user, change, ci_type, ci, article, related]); db.flush()
    link_change(article.id, change.id, db, user); link_ci(article.id, ci.id, db, user); link_related(article.id, related.id, db, user)
    with pytest.raises(Exception, match="already exists"):
        link_change(article.id, change.id, db, user)
    with pytest.raises(Exception, match="cannot be related"):
        link_related(article.id, article.id, db, user)
    submit_feedback(article.id, FeedbackPayload(helpful=True), db, user)
    submit_feedback(article.id, FeedbackPayload(helpful=True), db, user)
    assert db.query(KnowledgeFeedback).filter_by(article_id=article.id, user_id=user.id).count() == 1
    assert article.helpful_count == 1 and article.not_helpful_count == 0
    get_article(article.id, db, user)
    assert article.view_count == 1
    unlink_change(article.id, change.id, db, user)
    assert db.query(KnowledgeChangeLink).filter_by(article_id=article.id, change_id=change.id).count() == 0
    assert db.get(ChangeRequest, change.id) is not None
    assert db.query(KnowledgeCILink).filter_by(article_id=article.id, ci_id=ci.id).count() == 1
    assert db.query(KnowledgeRelatedLink).filter_by(article_id=article.id, related_article_id=related.id).count() == 1
