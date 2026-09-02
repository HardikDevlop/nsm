from backend.api.knowledge_routes import ArticleCreatePayload, ArticleUpdatePayload, router


def test_article_supports_known_errors_and_typed_nms_links():
    payload = ArticleCreatePayload(title="BGP flap workaround", article_type="known_error", body="Reset peer", incident_ids=[1], problem_ids=[2], device_ids=[3], service_ids=[4])
    assert payload.article_type == "known_error"
    assert payload.service_ids == [4]


def test_article_update_supports_versioned_publish_lifecycle():
    assert ArticleUpdatePayload(status="published", body="New revision").status == "published"


def test_knowledge_routes_cover_search_versions_and_updates():
    paths = {route.path for route in router.routes}
    assert "/api/v1/knowledge" in paths
    assert "/api/v1/knowledge/{article_id}" in paths
    assert "/api/v1/knowledge/{article_id}/versions" in paths
