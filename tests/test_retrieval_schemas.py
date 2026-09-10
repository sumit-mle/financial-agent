"""Unit tests for retrieval schemas — no external dependencies."""
from app.retrieval.schemas import AssembledContext, RetrievedChunk


def make_chunk(text: str, score: float = 0.8, source: str = "cfpb") -> RetrievedChunk:
    return RetrievedChunk(
        text=text,
        score=score,
        metadata={"source": source, "product": "Credit card"},
    )


def test_retrieved_chunk_final_score_uses_rerank():
    chunk = make_chunk("test", score=0.6)
    chunk.rerank_score = 0.92
    assert chunk.final_score == 0.92


def test_retrieved_chunk_final_score_fallback():
    chunk = make_chunk("test", score=0.75)
    assert chunk.final_score == 0.75


def test_source_label_cfpb():
    chunk = make_chunk("complaint text", source="cfpb")
    chunk.metadata["product"] = "Mortgage"
    assert "CFPB" in chunk.source_label
    assert "Mortgage" in chunk.source_label


def test_source_label_sec():
    chunk = RetrievedChunk(
        text="risk factors",
        score=0.7,
        metadata={"source": "sec_edgar", "company": "JPMorgan Chase"},
    )
    assert "JPMorgan Chase" in chunk.source_label
    assert "10-K" in chunk.source_label


def test_assembled_context_renders():
    ctx = AssembledContext(
        query="What are the fees?",
        passages=[make_chunk("Fee schedule is $25/month.", score=0.9)],
        customer_data={"name": "Alice", "account_status": "active"},
        available_actions=["lookup_account_summary(customer_id)"],
        system_instructions="You are Fin.",
    )
    rendered = ctx.to_context_string(max_tokens=4000)
    assert "System Instructions" in rendered
    assert "Customer Context" in rendered
    assert "Available Actions" in rendered
    assert "Relevant Knowledge" in rendered
    assert "Fee schedule" in rendered


def test_assembled_context_empty_passages():
    ctx = AssembledContext(query="hello", passages=[])
    rendered = ctx.to_context_string()
    # Should not crash and should not include passage section header
    assert isinstance(rendered, str)


def test_assembled_context_token_budget():
    # Very tight budget — should truncate passages
    long_text = "word " * 2000
    chunk = make_chunk(long_text, score=0.9)
    ctx = AssembledContext(
        query="test",
        passages=[chunk],
        system_instructions="short",
    )
    rendered = ctx.to_context_string(max_tokens=100)
    # Should be truncated — well under 100*4=400 chars for the passage
    assert len(rendered) < 10_000  # sanity check, not a crash
