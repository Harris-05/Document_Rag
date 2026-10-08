import io
import zipfile

from fastapi.testclient import TestClient

from app.config import get_settings

from .conftest import (
    CONTRACT_SENTENCE,
    DOCX_TYPE,
    PDF_TYPE,
    make_blank_pdf,
    make_docx,
    make_encrypted_pdf,
    make_image_only_pdf,
    make_mixed_pdf,
    make_text_pdf,
)


def upload(client: TestClient, name: str, content: bytes, content_type: str = PDF_TYPE):
    return client.post("/api/documents", files={"file": (name, io.BytesIO(content), content_type)})


def finished(client: TestClient, response) -> dict:
    """Background tasks complete before TestClient returns, so one GET reflects the final state."""
    assert response.status_code == 202, response.text
    return client.get(f"/api/documents/{response.json()['id']}").json()


def upload_files_on_disk() -> list:
    return list(get_settings().uploads_dir.iterdir())


class TestSuccessfulUploads:
    def test_pdf_is_extracted_page_by_page(self, client):
        document = finished(client, upload(client, "msa.pdf", make_text_pdf(3)))

        assert document["status"] == "ready"
        assert document["page_count"] == 3
        assert document["empty_page_count"] == 0
        assert document["word_count"] > 0

        text = client.get(f"/api/documents/{document['id']}/text").json()
        assert [page["page_number"] for page in text["pages"]] == [1, 2, 3]
        assert CONTRACT_SENTENCE in text["pages"][1]["text"]

    def test_docx_is_extracted(self, client):
        content = make_docx(["Governing law", CONTRACT_SENTENCE])
        document = finished(client, upload(client, "nda.docx", content, DOCX_TYPE))

        assert document["status"] == "ready"
        assert document["file_kind"] == "docx"
        text = client.get(f"/api/documents/{document['id']}/text").json()
        assert CONTRACT_SENTENCE in text["pages"][0]["text"]

    def test_pdf_with_some_blank_pages_is_flagged_not_hidden(self, client):
        document = finished(client, upload(client, "partly-scanned.pdf", make_mixed_pdf()))

        assert document["status"] == "ready"
        assert document["page_count"] == 2
        assert document["empty_page_count"] == 1

    def test_extension_match_is_case_insensitive(self, client):
        document = finished(client, upload(client, "MSA.PDF", make_text_pdf(1)))
        assert document["status"] == "ready"


class TestDocumentsWithNoReadableText:
    def test_blank_pdf_is_reported_and_not_saved(self, client):
        document = finished(client, upload(client, "blank.pdf", make_blank_pdf()))

        assert document["status"] == "failed"
        assert document["error_code"] == "NO_TEXT"
        assert "scan" in document["error_message"].lower()
        assert client.get("/api/documents").json() == []
        assert client.get(f"/api/documents/{document['id']}/text").status_code == 404
        assert upload_files_on_disk() == []

    def test_image_only_pdf_is_treated_as_empty(self, client):
        document = finished(client, upload(client, "scan.pdf", make_image_only_pdf()))
        assert document["error_code"] == "NO_TEXT"

    def test_docx_without_text_is_rejected(self, client):
        document = finished(client, upload(client, "empty.docx", make_docx([]), DOCX_TYPE))

        assert document["status"] == "failed"
        assert document["error_code"] == "NO_TEXT"
        assert client.get("/api/documents").json() == []


class TestRejectedUploads:
    def test_unsupported_extension(self, client):
        response = upload(client, "budget.xlsx", b"whatever", "application/vnd.ms-excel")

        assert response.status_code == 415
        assert response.json()["code"] == "UNSUPPORTED_TYPE"
        assert "budget.xlsx" in response.json()["message"]
        assert upload_files_on_disk() == []

    def test_renamed_file_with_wrong_contents(self, client):
        response = upload(client, "notes.pdf", b"just some plain text, not a pdf")

        assert response.status_code == 415
        assert response.json()["code"] == "UNSUPPORTED_TYPE"
        assert upload_files_on_disk() == []

    def test_zip_container_that_is_not_word(self, client):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("xl/workbook.xml", "<workbook/>")
        response = upload(client, "sheet.docx", buffer.getvalue(), DOCX_TYPE)

        assert response.status_code == 415
        assert response.json()["code"] == "UNSUPPORTED_TYPE"

    def test_empty_file(self, client):
        response = upload(client, "empty.pdf", b"")

        assert response.status_code == 422
        assert response.json()["code"] == "EMPTY_FILE"

    def test_file_over_the_size_limit(self, client):
        response = upload(client, "huge.pdf", b"%PDF-1.4\n" + b"0" * (1024 * 1024 + 10))

        assert response.status_code == 413
        assert response.json()["code"] == "FILE_TOO_LARGE"
        assert upload_files_on_disk() == []

    def test_password_protected_pdf(self, client):
        document = finished(client, upload(client, "locked.pdf", make_encrypted_pdf()))

        assert document["status"] == "failed"
        assert document["error_code"] == "PASSWORD_PROTECTED"

    def test_corrupt_pdf(self, client):
        document = finished(client, upload(client, "broken.pdf", b"%PDF-1.7\nthis is not a real pdf"))

        assert document["status"] == "failed"
        assert document["error_code"] == "CORRUPT_FILE"
        assert upload_files_on_disk() == []

    def test_missing_file_field(self, client):
        assert client.post("/api/documents").status_code == 422


class TestLibrary:
    def test_lists_newest_first_and_hides_failures(self, client):
        first = finished(client, upload(client, "first.pdf", make_text_pdf(1)))
        finished(client, upload(client, "blank.pdf", make_blank_pdf()))
        second = finished(client, upload(client, "second.pdf", make_text_pdf(2)))

        listed = client.get("/api/documents").json()
        assert [item["id"] for item in listed] == [second["id"], first["id"]]

    def test_delete_removes_record_pages_and_file(self, client):
        document = finished(client, upload(client, "msa.pdf", make_text_pdf(2)))
        assert len(upload_files_on_disk()) == 1

        assert client.delete(f"/api/documents/{document['id']}").status_code == 204
        assert client.get(f"/api/documents/{document['id']}").status_code == 404
        assert client.get("/api/documents").json() == []
        assert upload_files_on_disk() == []

    def test_delete_unknown_document(self, client):
        assert client.delete("/api/documents/nope").status_code == 404

    def test_filename_paths_are_stripped(self, client):
        document = finished(client, upload(client, r"C:\Users\someone\secret\msa.pdf", make_text_pdf(1)))
        assert document["filename"] == "msa.pdf"

    def test_documents_survive_a_restart(self, client):
        document = finished(client, upload(client, "msa.pdf", make_text_pdf(1)))

        with TestClient(client.app) as restarted:
            listed = restarted.get("/api/documents").json()
        assert [item["id"] for item in listed] == [document["id"]]

    def test_jobs_killed_mid_processing_are_failed_on_startup(self, client):
        from app import repository

        repository.create_document("stuck", "stuck.pdf", "pdf", 10)

        with TestClient(client.app) as restarted:
            stuck = restarted.get("/api/documents/stuck").json()
        assert stuck["status"] == "failed"
        assert stuck["error_code"] == "INTERRUPTED"
