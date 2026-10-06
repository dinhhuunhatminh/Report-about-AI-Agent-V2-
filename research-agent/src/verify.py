"""Kiểm tra trích dẫn BẰNG CODE: LLM nói trích dẫn là nguyên văn, code xác nhận có thật hay không.

Đây là điểm mạnh của bài tra cứu: trích dẫn kiểm chứng được máy móc, không cần tin lời model.

Mỗi trích dẫn (doc_id + quote) được xếp vào một trong các trạng thái:
  ok               quote nằm nguyên văn trong tài liệu VÀ agent đã thực sự nhìn thấy đoạn đó
  unknown_doc      doc_id không có trong kho
  not_in_document  quote không nằm trong tài liệu: bịa, diễn đạt lại hoặc dịch (lỗi phổ biến nhất)
  not_seen         quote có trong tài liệu nhưng agent chưa từng đọc đoạn đó (viết từ trí nhớ của model)

So khớp bỏ qua khác biệt về khoảng trắng và hoa/thường. Một quote được phép chứa "..." để
nối các đoạn rời; mỗi đoạn phải khớp riêng.

Câu trả lời không có trích dẫn chỉ được chấp nhận khi nói rõ là không tìm thấy thông tin.
"""
import re

from tools.corpus import fold, load_corpus

MIN_FRAGMENT = 8
NO_INFO_MARKERS = ("khong tim thay", "khong co thong tin", "khong duoc de cap", "khong neu", "khong co trong tai lieu")


# Dấu nháy và gạch "kiểu in" hay bị đổi thành dấu thường khi model chép lại; coi chúng là một.
_TYPOGRAPHY = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"',
                             "–": "-", "—": "-", "−": "-"})


def _norm(text):
    return re.sub(r"\s+", " ", text.translate(_TYPOGRAPHY)).strip().casefold()


def _fragments(quote):
    parts = re.split(r"\.\.\.|…", quote)
    frags = [_norm(p).strip(" \"'“”") for p in parts]
    frags = [f for f in frags if len(f) >= MIN_FRAGMENT]
    return frags or [_norm(quote).strip(" \"'“”")]


def seen_norm(history):
    """Văn bản agent THỰC SỰ đã nhìn thấy trong lần chạy này (kết quả tool thành công), đã chuẩn hóa.

    Chú ý: trí nhớ dài hạn KHÔNG nằm ở đây, nên không bao giờ được tính là "đã đọc"
    và không thể dùng làm nguồn trích dẫn.
    """
    return _norm("\n".join(e["result"] for e in history if e["ok"]))


def check_quote(doc_id, quote, seen, docs):
    if doc_id not in docs:
        return "unknown_doc"
    frags = _fragments(quote)
    doc_norm = _norm(docs[doc_id]["text"])
    if not all(f in doc_norm for f in frags):
        return "not_in_document"
    if not all(f in seen for f in frags):
        return "not_seen"
    return "ok"


def check_finish(args, history, docs=None):
    """Kiểm tra lời gọi finish. Trả về dict: ok, citations (kèm status), problems, message.

    `history` là các bước đã làm; "đã nhìn thấy" = nằm trong kết quả tool thành công của lần chạy này.
    `docs` là các nguồn có thể trích dẫn: kho nội bộ + các trang web đã tải trong lần chạy này
    (khóa là doc_id hoặc URL). Mặc định chỉ có kho nội bộ.
    """
    docs = load_corpus() if docs is None else docs
    seen = seen_norm(history)
    answer, citations = args["answer"], args["citations"]

    checked, problems = [], []
    for i, c in enumerate(citations, start=1):
        status = check_quote(c["doc_id"], c["quote"], seen, docs)
        checked.append({"doc_id": c["doc_id"], "quote": c["quote"], "status": status})
        if status != "ok":
            problems.append(f"trích dẫn #{i} ({c['doc_id']}): {explain(status)}")

    kinds = {c["status"] for c in checked if c["status"] != "ok"}
    if not citations and not any(m in fold(answer) for m in NO_INFO_MARKERS):
        problems.append("câu trả lời không có trích dẫn nào nhưng cũng không nói rõ là không tìm thấy thông tin")
        kinds.add("no_citation")

    message = ""
    if problems:
        message = ("KIỂM TRA TRÍCH DẪN THẤT BẠI: " + "; ".join(problems) +
                   ". Hãy đọc lại tài liệu (read_document) và copy NGUYÊN VĂN, hoặc bỏ nhận định không có căn cứ, "
                   "hoặc nói rõ là không tìm thấy thông tin.")
    return {"ok": not problems, "citations": checked, "problems": problems, "message": message,
            "kinds": sorted(kinds)}


def explain(status):
    return {
        "unknown_doc": "mã tài liệu không có trong kho, hoặc URL này chưa được tải bằng fetch_url trong lần chạy này",
        "not_in_document": "đoạn trích KHÔNG nằm nguyên văn trong tài liệu (có thể bị diễn đạt lại hoặc bịa)",
        "not_seen": "đoạn trích có trong tài liệu nhưng bạn chưa đọc đoạn đó trong lần chạy này",
    }.get(status, status)
