"""One-line text rendering for TSV fields, digests, and CLI tables."""

def one_line(value, limit: int = 60) -> str:
    """Collapse whitespace to single spaces and truncate with an ellipsis."""
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 3] + "..."
