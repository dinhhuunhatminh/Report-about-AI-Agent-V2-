"""Hai tool đọc kho tài liệu cục bộ: search_corpus (tìm) và read_document (đọc).

Kho tài liệu là các file .md trong thư mục research-agent/corpus/. Mỗi file là một tài liệu,
mã tài liệu (doc_id) chính là tên file bỏ đuôi, ví dụ '04-memory'.

An toàn: doc_id chỉ được dùng để tra trong từ điển đã nạp sẵn, KHÔNG bao giờ ghép vào đường dẫn
file. Vì vậy LLM không thể đọc file ngoài kho dù gửi doc_id kiểu '../../.env'.
"""
import re
import unicodedata
from pathlib import Path

CORPUS_DIR = Path(__file__).resolve().parents[2] / "corpus"
PAGE_SIZE = 3000          # số ký tự trả về mỗi lần đọc
SNIPPET_RADIUS = 110      # số ký tự lấy quanh chỗ khớp để làm đoạn trích

# Từ quá phổ biến (đã bỏ dấu), bỏ qua khi tìm để kết quả không bị nhiễu.
STOPWORDS = {
    "la", "gi", "cua", "va", "de", "cho", "trong", "khi", "co", "khong", "the", "nao", "mot",
    "cac", "nhung", "duoc", "bang", "thi", "ra", "voi", "nhu", "sao", "hay", "nay", "do", "o",
}

_cache = None


def _fold_char(c):
    """Bỏ dấu một ký tự và đổi sang chữ thường, luôn trả về ĐÚNG một ký tự.
    Nhờ vậy vị trí trong chuỗi đã bỏ dấu khớp từng ký tự với chuỗi gốc."""
    if c in "đĐ":
        return "d"
    return unicodedata.normalize("NFD", c)[0].lower()


def fold(text):
    return "".join(_fold_char(c) for c in text)


def load_corpus():
    """Nạp toàn bộ kho một lần: {doc_id: {title, text, folded}}."""
    global _cache
    if _cache is None:
        docs = {}
        for path in sorted(CORPUS_DIR.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            first = text.strip().splitlines()[0] if text.strip() else path.stem
            docs[path.stem] = {"title": first.lstrip("# ").strip(), "text": text, "folded": fold(text)}
        _cache = docs
    return _cache


def search_corpus(query, limit=5):
    docs = load_corpus()
    tokens = [t for t in re.findall(r"\w+", fold(query)) if len(t) >= 2 and t not in STOPWORDS]
    if not tokens:
        return "Từ khóa quá chung chung. Hãy dùng từ khóa cụ thể hơn."

    scored = []
    for doc_id, doc in docs.items():
        title_folded = fold(doc["title"])
        score = 0
        first_hit = None
        for tok in tokens:
            count = doc["folded"].count(tok)
            score += min(count, 5) + (3 if tok in title_folded else 0)
            if count and (first_hit is None or doc["folded"].find(tok) < first_hit):
                first_hit = doc["folded"].find(tok)
        if score > 0:
            scored.append((score, doc_id, first_hit))

    if not scored:
        return "Không có tài liệu nào khớp. Thử từ khóa khác (ví dụ tên khái niệm, thuật ngữ)."

    scored.sort(key=lambda x: (-x[0], x[1]))
    lines = []
    for score, doc_id, hit in scored[:limit]:
        text = docs[doc_id]["text"]
        start = max(0, (hit or 0) - SNIPPET_RADIUS)
        snippet = " ".join(text[start:start + 2 * SNIPPET_RADIUS].split())
        lines.append(f"- {doc_id} | {docs[doc_id]['title']} | điểm {score}\n    ...{snippet}...")
    return "\n".join(lines)


def read_document(doc_id, start=0):
    docs = load_corpus()
    if doc_id not in docs:
        return f"LỖI: không có tài liệu '{doc_id}'. Các mã hợp lệ: {', '.join(docs)}"
    text = docs[doc_id]["text"]
    total = len(text)
    if start >= total:
        return f"LỖI: start={start} vượt quá độ dài tài liệu ({total} ký tự)."
    end = min(start + PAGE_SIZE, total)
    header = f"[{doc_id}] {docs[doc_id]['title']} - ký tự {start}-{end} / {total}"
    footer = "" if end >= total else f"\n(còn tiếp: gọi lại read_document với start={end})"
    return f"{header}\n{text[start:end]}{footer}"
