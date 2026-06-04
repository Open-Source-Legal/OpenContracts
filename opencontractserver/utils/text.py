import re


def only_alphanumeric_chars(raw_str: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]", "", raw_str)


def truncate(text: str | None, max_length: int, suffix: str = "") -> str:
    """Truncate *text* to at most *max_length* characters.

    Parameters
    ----------
    text:
        The input string.  ``None`` and empty strings are returned as ``""``.
    max_length:
        Hard upper bound on the returned string's length (inclusive of
        *suffix* when truncation occurs).
    suffix:
        Optional string appended when the text is truncated (e.g. ``"..."``).
        The suffix replaces the tail of the text so the total length never
        exceeds *max_length*.

    Returns
    -------
    str
        The (possibly truncated) text.
    """
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    if suffix:
        cut = max_length - len(suffix)
        if cut <= 0:
            return suffix[:max_length]
        return text[:cut] + suffix
    return text[:max_length]


def truncate_middle(text: str | None, head: int, tail: int, marker: str = "…") -> str:
    """Truncate *text* keeping its first *head* and last *tail* characters.

    Unlike :func:`truncate`, this preserves both ends of a long string joined by
    *marker*, so a debug/report preview of a long span shows where it started
    *and* where it ended (e.g. for reconstructing which annotation failed).
    ``None``/empty input returns ``""``; short input is returned unchanged.
    """
    if not text:
        return ""
    if len(text) <= head + tail + len(marker):
        return text
    return text[:head] + marker + text[-tail:]
