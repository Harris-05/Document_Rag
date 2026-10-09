from app.rag.chunking import chunk_page, chunk_pages


def test_short_page_becomes_one_chunk():
    chunks = chunk_page(4, "Governing law. This Agreement is governed by English law.", 1000, 100)

    assert len(chunks) == 1
    assert chunks[0].page_number == 4


def test_empty_pages_produce_no_chunks():
    assert chunk_page(1, "   \n\n  ", 1000, 100) == []
    assert chunk_pages([(1, ""), (2, "")], 1000, 100) == []


def test_chunks_respect_the_size_target():
    sentence = "The Supplier shall perform the Services with reasonable skill and care. "
    chunks = chunk_page(1, sentence * 60, 500, 80)

    assert len(chunks) > 3
    assert all(len(chunk.text) <= 500 + 80 + 4 for chunk in chunks)


def test_no_text_is_lost_across_chunks():
    sentences = [f"Clause {i} sets out obligation number {i} for the Supplier." for i in range(80)]
    chunks = chunk_page(1, " ".join(sentences), 400, 60)
    joined = " ".join(chunk.text for chunk in chunks)

    assert all(sentence in joined for sentence in sentences)


def test_consecutive_chunks_overlap():
    sentences = [f"Obligation {i} applies to the Supplier in every case." for i in range(40)]
    chunks = chunk_page(1, "\n\n".join(sentences), 300, 90)

    assert len(chunks) > 2
    first_tail = chunks[0].text[-40:]
    assert first_tail in chunks[1].text


def test_chunks_never_cross_pages():
    chunks = chunk_pages([(1, "Page one clause text."), (2, "Page two clause text.")], 1000, 100)

    assert [(c.page_number, c.text) for c in chunks] == [
        (1, "Page one clause text."),
        (2, "Page two clause text."),
    ]


def test_a_single_unbroken_run_is_still_split():
    chunks = chunk_page(1, "word " * 600, 300, 50)
    assert len(chunks) > 5
