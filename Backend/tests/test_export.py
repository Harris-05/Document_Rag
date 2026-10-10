"""Exporting an answer with its quotes as a PDF or Word file."""

import io
import json

import pytest
from docx import Document
from fastapi.testclient import TestClient
from pypdf import PdfReader

from app import chat_repository, conversation_repository, repository
from app.export.content import build_content, split_answer
from app.export.pdf import render_pdf
from app.export.word import render_docx
from app.schemas import ChatMessage, Citation

from .conftest import PDF_TYPE, make_text_pdf

EXPLANATION = "General explanation (not from the document):"
ANSWER = (
    "Either party may terminate on ninety days notice [1]. Liability is capped at AED 100,000 [2].\n\n"
    f"{EXPLANATION} In general, a cap limits exposure.\n"
)


def citation(n: int, quote: str, verified: bool = True, page: int | None = 2, **extra) -> dict:
    return {
        "n": n,
        "quote": quote,
        "verified": verified,
        "page": page if verified else None,
        "ranges": [],
        "occurrences": 1 if verified else 0,
        **extra,
    }


def message(content: str = ANSWER, status: str = "complete", citations: list[dict] | None = None, quality: str = "sufficient"):
    cites = citations if citations is not None else [
        citation(1, "may terminate this Agreement for convenience"),
        citation(2, "not exceed AED 100,000 in any contract year", verified=False),
    ]
    return ChatMessage(
        id=1,
        role="assistant",
        content=content,
        status=status,
        quality=quality,
        citations=[Citation(**c) for c in cites],
        trace=[],
        coverage=None,
        error_message=None,
        created_at="2026-01-01T00:00:00",
    )


def pdf_text(data: bytes) -> str:
    return "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(data)).pages)


def docx_text(data: bytes) -> str:
    return "\n".join(p.text for p in Document(io.BytesIO(data)).paragraphs)


class TestContent:
    def test_the_general_explanation_is_kept_apart_from_the_document_answer(self):
        answer, explanation = split_answer(ANSWER)
        assert answer.startswith("Either party may terminate") and EXPLANATION not in answer
        assert explanation == "In general, a cap limits exposure."

    def test_an_answer_without_an_explanation_has_none(self):
        assert split_answer("Just the answer [1].")[1] is None

    def test_quotes_are_listed_in_order_with_their_status(self):
        content = build_content(message(), "Can they terminate?", ["msa.pdf"], multi=False)
        assert [(q.n, q.verified) for q in content.quotes] == [(1, True), (2, False)]
        assert content.evidence == "Strong evidence"
        assert content.filename_stem == "answer-can-they-terminate"

    def test_a_missing_question_is_stated_not_invented(self):
        assert build_content(message(), None, [], multi=False).question == "(question not available)"


@pytest.mark.parametrize(("render", "extract"), [(render_pdf, pdf_text), (render_docx, docx_text)])
class TestBothFormats:
    def build(self, render, **kwargs):
        content = build_content(
            kwargs.pop("msg", message()), kwargs.pop("question", "Can either party terminate?"), kwargs.pop("docs", ["msa.pdf"]), kwargs.pop("multi", False)
        )
        return render(content)

    def test_contains_the_question_answer_and_every_quote(self, render, extract):
        text = extract(self.build(render))
        for expected in ("Can either party terminate?", "ninety days notice [1]", "may terminate this Agreement for convenience", "AED 100,000"):
            assert expected in " ".join(text.split())

    def test_says_which_quotes_were_verified_and_where(self, render, extract):
        text = " ".join(extract(self.build(render)).split())
        assert "Verified" in text and "page 2" in text
        assert "Not verified" in text

    def test_general_explanation_is_labelled_as_not_from_the_document(self, render, extract):
        text = " ".join(extract(self.build(render)).split())
        assert "General explanation (not from the document)" in text
        assert "It is not from the document" in text

    def test_a_stopped_answer_says_it_may_be_incomplete(self, render, extract):
        text = " ".join(extract(self.build(render, msg=message(status="stopped"))).split())
        assert "stopped before it finished" in text

    def test_a_multi_document_answer_names_the_document_of_each_quote(self, render, extract):
        cites = [citation(1, "ninety (90) days", document_name="msa_2021.pdf"), citation(2, "thirty (30) days", document_name="msa_2024.pdf")]
        text = " ".join(extract(self.build(render, msg=message(citations=cites), docs=["msa_2021.pdf", "msa_2024.pdf"], multi=True)).split())
        assert "msa_2021.pdf" in text and "msa_2024.pdf" in text and "Documents:" in text

    def test_an_answer_with_no_quotes_says_so(self, render, extract):
        text = " ".join(extract(self.build(render, msg=message(citations=[]))).split())
        assert "no quotes" in text

    def test_special_characters_do_not_break_it(self, render, extract):
        odd = message(content="Naïve “curly” – dashes … <b>tags</b> & ampersands [1].", citations=[citation(1, "café “x” & <y>")])
        assert len(self.build(render, msg=odd)) > 500

    def test_a_long_answer_runs_over_several_pages(self, render, extract):
        long = message(content="\n\n".join(f"Paragraph {i} " + "word " * 120 + f"[{1}]" for i in range(40)))
        data = self.build(render, msg=long)
        if render is render_pdf:
            assert len(PdfReader(io.BytesIO(data)).pages) > 2
        assert "Paragraph 39" in extract(data)


class TestEndpoint:
    @pytest.fixture
    def saved(self, client: TestClient):
        response = client.post("/api/documents", files={"file": ("msa.pdf", io.BytesIO(make_text_pdf(2)), PDF_TYPE)})
        document_id = response.json()["id"]
        conversation_id = conversation_repository.ensure_single(document_id)
        chat_repository.add_user_message(conversation_id, "Who indemnifies whom?")
        cites = [citation(1, "shall indemnify the Customer", document_id=document_id, document_name="msa.pdf")]
        answer_id = chat_repository.add_assistant_message(
            conversation_id, content="The Supplier indemnifies [1].", status="complete", quality="sufficient", citations=cites, trace=[], coverage=None
        )
        failed_id = chat_repository.add_assistant_message(
            conversation_id, content="", status="error", quality=None, citations=[], trace=[], coverage=None, error_message="boom"
        )
        user_id = chat_repository.add_user_message(conversation_id, "another question")
        return {"answer": answer_id, "failed": failed_id, "user": user_id}

    def test_downloads_a_pdf_with_the_question_that_was_asked(self, client, saved):
        response = client.get(f"/api/messages/{saved['answer']}/export?format=pdf")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert 'filename="answer-who-indemnifies-whom.pdf"' in response.headers["content-disposition"]
        assert response.content.startswith(b"%PDF")
        text = " ".join(pdf_text(response.content).split())
        assert "Who indemnifies whom?" in text and "msa.pdf" in text

    def test_downloads_a_word_file(self, client, saved):
        response = client.get(f"/api/messages/{saved['answer']}/export?format=docx")
        assert response.status_code == 200
        assert response.headers["content-type"].endswith("wordprocessingml.document")
        assert "Who indemnifies whom?" in docx_text(response.content)

    def test_pdf_is_the_default_format(self, client, saved):
        assert client.get(f"/api/messages/{saved['answer']}/export").headers["content-type"] == "application/pdf"

    def test_an_unknown_format_is_rejected(self, client, saved):
        assert client.get(f"/api/messages/{saved['answer']}/export?format=exe").status_code == 422

    def test_an_unknown_answer_is_not_found(self, client, saved):
        assert client.get("/api/messages/999999/export").status_code == 404

    def test_a_failed_answer_and_a_question_cannot_be_exported(self, client, saved):
        assert client.get(f"/api/messages/{saved['failed']}/export").status_code == 409
        assert client.get(f"/api/messages/{saved['user']}/export").status_code == 409

    def test_the_filename_header_is_readable_by_the_browser_app(self, client, saved):
        response = client.get(
            f"/api/messages/{saved['answer']}/export", headers={"Origin": "http://localhost:3000"}
        )
        assert "content-disposition" in response.headers["access-control-expose-headers"].lower()
