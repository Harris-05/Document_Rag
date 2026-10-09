import io
import json

import pytest
from fastapi.testclient import TestClient
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app import chat_repository, conversation_repository, repository
from app.config import get_settings
from app.db import SCHEMA_VERSION, connect, init_db
from app.dependencies import get_llm
from app.main import app

from .conftest import PDF_TYPE
from .fakes import ScriptedMultiGrader
from .test_documents_api import finished, upload
from .test_multi_agent import comparison, judge, plan

SENTENCE_A = "Either party may terminate on ninety (90) days written notice."
SENTENCE_B = "Either party may terminate on thirty (30) days written notice."


def make_pdf(*lines: str) -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    pdf.setFont("Helvetica", 11)
    for number, line in enumerate(lines):
        pdf.drawString(72, 760 - number * 24, line)
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def parse_sse(body: str) -> list[tuple[str, dict]]:
    events = []
    for frame in body.strip().split("\n\n"):
        lines = frame.splitlines()
        events.append((lines[0].removeprefix("event: "), json.loads(lines[1].removeprefix("data: "))))
    return events


@pytest.fixture
def use_llm(client):
    def install(llm):
        app.dependency_overrides[get_llm] = lambda: llm
        return llm

    yield install
    app.dependency_overrides.pop(get_llm, None)


@pytest.fixture
def documents(client: TestClient) -> dict[str, str]:
    ids = {}
    for key, name, sentence in (("a", "msa_a.pdf", SENTENCE_A), ("b", "msa_b.pdf", SENTENCE_B)):
        ids[key] = finished(client, upload(client, name, make_pdf("1. Termination", sentence), PDF_TYPE))["id"]
    return ids


def create(client: TestClient, *ids: str):
    return client.post("/api/conversations", json={"document_ids": list(ids)})


def scripted_comparison() -> ScriptedMultiGrader:
    return ScriptedMultiGrader(
        plans=[plan("terminate notice")],
        grades=[judge({"D1": 2, "D2": 2}, {"D1": True, "D2": True})],
        answer_for=comparison([("D1", None, SENTENCE_A), ("D2", None, SENTENCE_B)]),
    )


class TestCreatingAConversation:
    def test_documents_are_kept_in_the_order_they_were_chosen(self, client, documents):
        response = create(client, documents["b"], documents["a"])

        assert response.status_code == 201
        body = response.json()
        assert body["kind"] == "multi"
        assert [d["id"] for d in body["documents"]] == [documents["b"], documents["a"]]

    def test_it_can_be_fetched_and_appears_in_the_list(self, client, documents):
        created = create(client, documents["a"], documents["b"]).json()

        assert client.get(f"/api/conversations/{created['id']}").json()["id"] == created["id"]
        assert [c["id"] for c in client.get("/api/conversations").json()] == [created["id"]]

    def test_at_least_two_documents_are_needed(self, client, documents):
        assert create(client, documents["a"]).status_code == 422
        assert create(client).status_code == 422

    def test_a_document_cannot_be_selected_twice(self, client, documents):
        assert create(client, documents["a"], documents["a"]).status_code == 422

    def test_there_is_a_limit_and_the_message_says_what_it_is(self, client, documents, monkeypatch):
        monkeypatch.setenv("MAX_DOCUMENTS_PER_QUESTION", "2")
        get_settings.cache_clear()
        third = finished(client, upload(client, "c.pdf", make_pdf("Another contract of sorts."), PDF_TYPE))["id"]

        response = create(client, documents["a"], documents["b"], third)

        assert response.status_code == 422
        assert response.json()["code"] == "TOO_MANY_DOCUMENTS"
        assert "up to 2 documents" in response.json()["message"]

    def test_an_unknown_document_is_rejected(self, client, documents):
        response = create(client, documents["a"], "does-not-exist")
        assert response.status_code == 404 and response.json()["code"] == "DOCUMENT_NOT_READY"

    def test_a_document_still_being_processed_is_rejected_by_name(self, client, documents):
        repository.create_document("busy", "busy.pdf", "pdf", 10)

        response = create(client, documents["a"], "busy")

        assert response.status_code == 422
        assert "busy.pdf" in response.json()["message"] and "still being processed" in response.json()["message"]

    def test_one_document_chats_are_not_exposed_as_comparisons(self, client, documents):
        single = conversation_repository.ensure_single(documents["a"])
        assert client.get(f"/api/conversations/{single}").status_code == 404
        assert client.get("/api/conversations").json() == []


class TestAskingAcrossDocuments:
    def test_the_answer_streams_and_each_quote_names_and_verifies_in_its_own_document(self, client, documents, use_llm):
        use_llm(scripted_comparison())
        conversation = create(client, documents["a"], documents["b"]).json()

        response = client.post(f"/api/conversations/{conversation['id']}/chat", json={"question": "Compare the notice periods"})

        assert response.status_code == 200
        events = parse_sse(response.text)
        assert events[0][0] == "start" and events[-1][0] == "done"
        citations = next(d for n, d in events if n == "citations")
        assert [(c["document_id"], c["verified"]) for c in citations] == [(documents["a"], True), (documents["b"], True)]
        assert all(c["matches"] and c["page"] == 1 for c in citations)
        done = events[-1][1]
        assert done["quality"] == "sufficient"
        assert [d["document_id"] for d in done["coverage"]["documents"]] == [documents["a"], documents["b"]]

    def test_the_conversation_is_saved_and_can_be_reopened_with_its_attributed_citations(self, client, documents, use_llm):
        use_llm(scripted_comparison())
        conversation = create(client, documents["a"], documents["b"]).json()
        client.post(f"/api/conversations/{conversation['id']}/chat", json={"question": "Compare the notice periods"})

        saved = client.get(f"/api/conversations/{conversation['id']}/messages").json()

        assert [m["role"] for m in saved] == ["user", "assistant"]
        assert [c["document_id"] for c in saved[1]["citations"]] == [documents["a"], documents["b"]]
        assert saved[1]["coverage"]["documents"][0]["evidence"] == "sufficient"
        assert client.get(f"/api/conversations/{conversation['id']}").json()["message_count"] == 2

    def test_a_comparison_does_not_leak_into_either_documents_own_chat(self, client, documents, use_llm):
        use_llm(scripted_comparison())
        conversation = create(client, documents["a"], documents["b"]).json()
        client.post(f"/api/conversations/{conversation['id']}/chat", json={"question": "Compare"})

        assert client.get(f"/api/documents/{documents['a']}/messages").json() == []
        assert client.get(f"/api/documents/{documents['b']}/messages").json() == []

    def test_follow_ups_remember_the_comparison(self, client, documents, use_llm):
        llm = use_llm(
            ScriptedMultiGrader(
                plans=[plan("terminate"), plan("terminate", standalone="Which notice period is shorter?")],
                grades=[judge({"D1": 2, "D2": 2}, True)] * 2,
                answer_for=comparison([("D1", None, SENTENCE_A), ("D2", None, SENTENCE_B)]),
            )
        )
        conversation = create(client, documents["a"], documents["b"]).json()
        client.post(f"/api/conversations/{conversation['id']}/chat", json={"question": "Compare the notice periods"})
        client.post(f"/api/conversations/{conversation['id']}/chat", json={"question": "Which is shorter?"})

        from app.rag import prompts

        assert "Compare the notice periods" in llm.prompts_for(prompts.QUERY_SYSTEM)[1]

    def test_asking_in_an_unknown_conversation(self, client, use_llm):
        use_llm(scripted_comparison())
        assert client.post("/api/conversations/nope/chat", json={"question": "hello"}).status_code == 404
        assert client.get("/api/conversations/nope/messages").status_code == 404

    def test_a_missing_ai_key_gives_the_same_clear_error_as_everywhere_else(self, client, documents, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPEN_AI_APIKEY", raising=False)
        settings = get_settings().model_copy(update={"openai_api_key": None})
        monkeypatch.setattr("app.dependencies.get_settings", lambda: settings)
        conversation = create(client, documents["a"], documents["b"]).json()

        response = client.post(f"/api/conversations/{conversation['id']}/chat", json={"question": "Compare"})

        assert response.status_code == 503 and response.json()["code"] == "AI_NOT_CONFIGURED"


class TestWhenDocumentsAreRemoved:
    def test_deleting_the_conversation_keeps_the_documents(self, client, documents):
        conversation = create(client, documents["a"], documents["b"]).json()

        assert client.delete(f"/api/conversations/{conversation['id']}").status_code == 204
        assert client.get(f"/api/conversations/{conversation['id']}").status_code == 404
        assert client.get(f"/api/documents/{documents['a']}").status_code == 200
        assert client.delete("/api/conversations/nope").status_code == 404

    def test_deleting_one_document_keeps_the_conversation_and_its_history(self, client, documents, use_llm):
        use_llm(scripted_comparison())
        conversation = create(client, documents["a"], documents["b"]).json()
        client.post(f"/api/conversations/{conversation['id']}/chat", json={"question": "Compare"})

        client.delete(f"/api/documents/{documents['a']}")

        kept = client.get(f"/api/conversations/{conversation['id']}").json()
        assert [d["id"] for d in kept["documents"]] == [documents["b"]]
        history = client.get(f"/api/conversations/{conversation['id']}/messages").json()
        assert len(history) == 2  # the earlier comparison is still readable

    def test_deleting_every_document_removes_the_conversation(self, client, documents):
        conversation = create(client, documents["a"], documents["b"]).json()

        client.delete(f"/api/documents/{documents['a']}")
        client.delete(f"/api/documents/{documents['b']}")

        assert client.get(f"/api/conversations/{conversation['id']}").status_code == 404

    def test_deleting_a_document_removes_its_own_chat_but_not_a_comparisons(self, client, documents, use_llm):
        conversation = create(client, documents["a"], documents["b"]).json()
        single = conversation_repository.ensure_single(documents["a"])

        client.delete(f"/api/documents/{documents['a']}")

        assert conversation_repository.get(single) is None
        assert conversation_repository.get(conversation["id"]) is not None


class TestUpgradingExistingChats:
    def test_chats_saved_before_conversations_existed_become_one_document_conversations(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
        get_settings.cache_clear()
        init_db()
        repository.create_document("old-doc", "old.pdf", "pdf", 10)

        # Recreate the previous layout: messages hung directly off a document.
        with connect() as connection:
            connection.execute("DROP TABLE messages")
            connection.execute("DROP TABLE conversation_documents")
            connection.execute("DROP TABLE conversations")
            connection.execute(
                """CREATE TABLE messages (id INTEGER PRIMARY KEY AUTOINCREMENT, document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                   role TEXT NOT NULL, content TEXT NOT NULL, status TEXT NOT NULL, quality TEXT, citations TEXT NOT NULL DEFAULT '[]',
                   trace TEXT NOT NULL DEFAULT '[]', coverage TEXT, error_message TEXT, created_at TEXT NOT NULL)"""
            )
            connection.execute(
                "INSERT INTO messages (document_id, role, content, status, created_at) VALUES ('old-doc', 'user', 'What is the term?', 'complete', '2026-01-01T00:00:00.000+00:00')"
            )
            connection.execute(
                "INSERT INTO messages (document_id, role, content, status, quality, created_at) VALUES ('old-doc', 'assistant', 'Two years.', 'complete', 'sufficient', '2026-01-01T00:00:01.000+00:00')"
            )
            connection.execute("PRAGMA user_version = 2")

        init_db()

        conversation_id = conversation_repository.single_conversation_id("old-doc")
        history = chat_repository.list_messages(conversation_id)
        assert [(m.role, m.content) for m in history] == [("user", "What is the term?"), ("assistant", "Two years.")]
        assert conversation_repository.get(conversation_id).documents[0].id == "old-doc"
        with connect() as connection:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            assert "messages_v2" not in tables
            assert connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        get_settings.cache_clear()

    def test_upgrading_twice_changes_nothing(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
        get_settings.cache_clear()
        init_db()
        repository.create_document("doc-x", "x.pdf", "pdf", 10)
        conversation_id = conversation_repository.ensure_single("doc-x")
        chat_repository.add_user_message(conversation_id, "hello")

        init_db()
        init_db()

        assert len(chat_repository.list_messages(conversation_id)) == 1
        get_settings.cache_clear()
