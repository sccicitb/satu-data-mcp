import html
import re

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t]+")


def strip_html(value: str | None) -> str:
    """Convert the HTML-bearing `deskripsi` field into clean plain text.

    The source uses <ul><li><strong>col:</strong> ...</li></ul> for column
    definitions, so list items are put on their own line to keep that
    structure legible instead of collapsing it into a single paragraph.
    """
    if not value:
        return ""
    text = re.sub(r"</li>", "\n", value)
    text = re.sub(r"<li>", "- ", text)
    text = re.sub(r"</p>", "\n\n", text)
    text = _TAG_RE.sub("", text)
    text = html.unescape(text)
    text = _WS_RE.sub(" ", text)
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()
