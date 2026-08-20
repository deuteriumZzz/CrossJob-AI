import re

_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(html: str) -> str:
    return _TAG_RE.sub(" ", html or "").strip()
