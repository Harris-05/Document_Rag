import pytest
from fastapi.testclient import TestClient

from app import comparison_repository, repository
from app.compare import prompts
from app.dependencies import get_optional_llm
from app.errors import ErrorCode
from app.main import app

from .conftest import PDF_TYPE
from .fakes import FakeLLM
from .test_compare_engine import items_in, sensible
from .test_conversations_api import make_pdf
from .test_documents_api import finished, upload

OLD_LINES = (
    "1.1 The Supplier shall provide the consulting services described in Schedule 1.",
    "2.1 The Customer shall pay each undisputed invoice within thirty (30) days of receiving a valid invoice.",
    "3.1 The Supplier's aggregate liability shall not exceed AED 100,000 in any contract year.",
)
NEW_LINES = (
    OLD_LINES[0],
    OLD_LINES[1],
    "3.1 The Supplier's aggregate liability shall not exceed AED 1,000,000 in any contract year.",
    "4.1 Each party shall comply with all applicable data protection laws when processing personal data.",
)


def scripted_rater(decide=sensible) -> FakeLLM:
    def handle(system: str, user: str) -> dict:
        if system == prompts.RATE_SYSTEM:
            return {
                "items": [
                    dict(zip(("significance", "category", "title", "summary"), decide(kind, body), strict=True), id=number)
                    for number, kind, body in items_in(user)
                ]
            }
        return {"headline": "The liability cap rose and a data protection clause was added.", "key_points": ["Cap: AED 100,000 to AED 1,000,000."]}

    return FakeLLM(json_handler=handle)


@pytest.fixture
def versions(client: TestClient) -> dict[str, str]:
    return {
        "old": finished(client, upload(client, "msa_v1.pdf", make_pdf(*OLD_LINES), PDF_TYPE))["id"],
        "new": finished(client, upload(client, "msa_v2.pdf", make_pdf(*NEW_LINES), PDF_TYPE))["id"],
    }


@pytest.fixture
def use_ai(client):
    def install(llm):
        app.dependency_overrides[get_optional_llm] = lambda: llm
        return llm

    yield install
    app.dependency_overrides.pop(get_optional_llm, None)


def start(client: TestClient, old: str, new: str):
    return client.post("/api/comparisons", json={"old_document_id": old, "new_document_id": new})


def result_of(client: TestClient, response) -> dict:
    assert response.status_code == 202, response.text
    return client.get(f"/api/comparisons/{response.json()['id']}").json()


class TestRunningAComparison:
    def test_it_starts_in_the_background_and_finishes_with_a_result(self, client, versions, use_ai):
        use_ai(scripted_rater())
        response = start(client, versions["old"], versions["new"])

        assert response.status_code == 202
        assert response.json()["status"] == "processing"
        body = client.get(f"/api/comparisons/{response.json()['id']}").json()

        assert body["status"] == "ready" and body["stage"] == "done"
        assert [body["old_document"]["filename"], body["new_document"]["filename"]] == ["msa_v1.pdf", "msa_v2.pdf"]
        assert body["stats"]["unchanged"] == 2 and body["stats"]["modified"] == 1 and body["stats"]["added"] == 1
        assert body["summary"]["headline"].startswith("The liability cap rose")
        assert body["ai_used"] is True and body["ai_notice"] is None

    def test_the_changes_carry_figures_text_positions_and_ratings(self, client, versions, use_ai):
        use_ai(scripted_rater())
        body = result_of(client, start(client, versions["old"], versions["new"]))
        by_type = {c["type"]: c for c in body["changes"]}

        liability = by_type["modified"]
        assert liability["significance"] == "critical" and liability["category"] == "liability"
        assert liability["figures"] == [{"kind": "money", "old": "AED 100,000", "new": "AED 1,000,000"}]
        assert "AED 100,000" in liability["old"]["text"] and "AED 1,000,000" in liability["new"]["text"]
        assert liability["old"]["ranges"][0]["page"] == 1
        assert any(s["op"] == "insert" and s["text"] == "1,000,000" for s in liability["diff"])
        assert by_type["added"]["old"] is None and by_type["added"]["new"]["text"].startswith("4.1 Each party")

    def test_a_model_cannot_talk_a_changed_figure_down_to_cosmetic(self, client, versions, use_ai):
        use_ai(scripted_rater(lambda kind, body: ("cosmetic", "other", "Anything", "Nothing important.")))
        liability = next(c for c in result_of(client, start(client, versions["old"], versions["new"]))["changes"] if c["type"] == "modified")

        assert liability["significance"] == "major" and liability["raised_by_rules"] is True

    def test_it_still_works_without_an_ai_key_and_says_so(self, client, versions, use_ai):
        use_ai(None)
        body = result_of(client, start(client, versions["old"], versions["new"]))
        by_type = {c["type"]: c for c in body["changes"]}

        assert body["status"] == "ready" and body["ai_used"] is False
        assert "not available" in body["ai_notice"] and body["summary"] is None
        assert by_type["modified"]["significance"] == "major"  # from the changed figure, by rules
        assert by_type["added"]["significance"] == "unrated"

    def test_identical_documents_have_nothing_to_report(self, client, versions, use_ai):
        use_ai(scripted_rater())
        twin = finished(client, upload(client, "msa_v1_copy.pdf", make_pdf(*OLD_LINES), PDF_TYPE))["id"]
        body = result_of(client, start(client, versions["old"], twin))

        assert body["changes"] == [] and body["stats"]["unchanged"] == 3


class TestValidation:
    def test_a_document_cannot_be_compared_with_itself(self, client, versions):
        response = start(client, versions["old"], versions["old"])
        assert response.status_code == 422 and response.json()["code"] == "SAME_DOCUMENT"

    def test_an_unknown_document_is_rejected(self, client, versions):
        response = start(client, versions["old"], "missing")
        assert response.status_code == 404 and response.json()["code"] == "DOCUMENT_NOT_READY"

    def test_a_document_still_processing_is_rejected_by_name(self, client, versions):
        repository.create_document("busy", "busy.pdf", "pdf", 10)
        response = start(client, versions["old"], "busy")

        assert response.status_code == 422 and "busy.pdf" in response.json()["message"]

    def test_both_documents_are_required(self, client):
        assert client.post("/api/comparisons", json={"old_document_id": "x"}).status_code == 422


class TestReuseAndLifecycle:
    def test_asking_again_for_the_same_pair_reuses_the_result_without_new_ai_calls(self, client, versions, use_ai):
        llm = use_ai(scripted_rater())
        first = start(client, versions["old"], versions["new"]).json()["id"]
        client.get(f"/api/comparisons/{first}")
        calls = llm.count(prompts.RATE_SYSTEM)

        second = start(client, versions["old"], versions["new"]).json()["id"]

        assert second == first
        assert llm.count(prompts.RATE_SYSTEM) == calls

    def test_the_reverse_order_is_a_different_comparison(self, client, versions, use_ai):
        use_ai(scripted_rater())
        forward = start(client, versions["old"], versions["new"]).json()["id"]
        backward = start(client, versions["new"], versions["old"]).json()["id"]
        body = client.get(f"/api/comparisons/{backward}").json()

        assert backward != forward
        assert body["stats"]["removed"] == 1 and body["stats"]["added"] == 0  # reading it the other way round

    def test_comparisons_are_listed_newest_first_and_can_be_deleted(self, client, versions, use_ai):
        use_ai(scripted_rater())
        first = start(client, versions["old"], versions["new"]).json()["id"]
        second = start(client, versions["new"], versions["old"]).json()["id"]

        assert [c["id"] for c in client.get("/api/comparisons").json()] == [second, first]
        assert client.delete(f"/api/comparisons/{first}").status_code == 204
        assert client.get(f"/api/comparisons/{first}").status_code == 404
        assert client.delete(f"/api/comparisons/{first}").status_code == 404
        assert client.get(f"/api/documents/{versions['old']}").status_code == 200  # the documents stay

    def test_deleting_either_document_removes_its_comparisons(self, client, versions, use_ai):
        use_ai(scripted_rater())
        comparison = start(client, versions["old"], versions["new"]).json()["id"]

        client.delete(f"/api/documents/{versions['new']}")

        assert client.get(f"/api/comparisons/{comparison}").status_code == 404
        assert client.get("/api/comparisons").json() == []

    def test_an_unknown_comparison_is_a_404(self, client):
        assert client.get("/api/comparisons/nope").status_code == 404

    def test_a_comparison_killed_by_a_restart_is_marked_failed_and_not_listed(self, client, versions):
        stuck = comparison_repository.create(versions["old"], versions["new"])

        with TestClient(client.app) as restarted:
            body = restarted.get(f"/api/comparisons/{stuck}").json()
            listed = restarted.get("/api/comparisons").json()

        assert body["status"] == "failed" and body["error_code"] == ErrorCode.INTERRUPTED.value
        assert listed == []

    def test_an_unexpected_failure_is_recorded_not_left_processing(self, client, versions, use_ai, monkeypatch):
        use_ai(None)

        async def boom(*args, **kwargs):
            raise RuntimeError("something broke")

        monkeypatch.setattr("app.routers.comparisons.compare_documents", boom)
        body = result_of(client, start(client, versions["old"], versions["new"]))

        assert body["status"] == "failed" and body["error_code"] == "INTERNAL"
        assert "Please try again" in body["error_message"]

    def test_a_failed_comparison_can_be_started_again(self, client, versions, use_ai, monkeypatch):
        use_ai(None)

        async def boom(*args, **kwargs):
            raise RuntimeError("x")

        with monkeypatch.context() as patch:
            patch.setattr("app.routers.comparisons.compare_documents", boom)
            failed = start(client, versions["old"], versions["new"]).json()["id"]
        retry = start(client, versions["old"], versions["new"]).json()["id"]

        assert retry != failed
        assert client.get(f"/api/comparisons/{retry}").json()["status"] == "ready"
