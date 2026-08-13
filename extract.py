"""从文档文件或 URL 提取纯文本。"""

import re

MAX_CHARS = 8000


def _truncate(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + "\n[内容过长，已截断]"
    return text


def extract_pdf(data: bytes) -> str:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(data)
    parts = []
    for page in pdf:
        parts.append(page.get_textpage().get_text_range())
    pdf.close()
    return _truncate("\n".join(parts))


def extract_docx(data: bytes) -> str:
    from io import BytesIO
    from docx import Document

    doc = Document(BytesIO(data))
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            parts.append("\t".join(c.text for c in row.cells))
    return _truncate("\n".join(parts))


def extract_plain(data: bytes) -> str:
    try:
        return _truncate(data.decode("utf-8"))
    except UnicodeDecodeError:
        return _truncate(data.decode("gbk", errors="ignore"))


def extract_url(url: str) -> str:
    import requests

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
    }
    resp = requests.get(url, headers=headers, timeout=20)
    resp.raise_for_status()
    html = resp.text
    html = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", html)
    html = re.sub(r"(?is)<br\s*/?>", "\n", html)
    html = re.sub(r"(?is)<[^>]+>", " ", html)
    html = re.sub(r"&nbsp;?", " ", html)
    html = re.sub(r"&amp;?", "&", html)
    html = re.sub(r"&lt;?", "<", html)
    html = re.sub(r"&gt;?", ">", html)
    return _truncate(html)


def extract_file_bytes(filename: str, data: bytes) -> str:
    name = filename.lower()
    if name.endswith(".pdf"):
        return extract_pdf(data)
    if name.endswith(".docx"):
        return extract_docx(data)
    if name.endswith(".txt") or name.endswith(".md"):
        return extract_plain(data)
    raise ValueError(f"不支持的文件类型：{filename}（支持 PDF / DOCX / TXT / MD）")
