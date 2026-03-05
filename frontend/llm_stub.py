"""
llm_stub.py — Placeholder for future LLM integration (Stage 5).

When a question doesn't match any predefined query, this is called.
Replace the body of llm_stub() with real LLM logic in Stage 5.
"""


def llm_stub(question: str) -> dict:
    """
    Stub response for unmatched questions.

    Future: replace with Kimi / OpenAI call that generates validated SQL.
    The generated SQL must still pass through the 5-layer validator
    before execution (same as Stage 3).

    Returns a dict — not an error, but an informational response.
    """
    return {
        "status" : "llm_required",
        "message": (
            "This question doesn't match any predefined report. "
            "LLM integration is planned for Stage 5. "
            "Try one of: 'show yearly revenue', 'quarterly data', "
            "'top profit companies', or 'revenue for C001'."
        ),
        "question": question,
        "suggestions": [
            "Show yearly revenue",
            "Show quarterly revenue",
            "Top 10 companies by profit",
            "Revenue for C001",
            "Show all data",
        ],
    }
