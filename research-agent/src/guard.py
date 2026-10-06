"""Khối GUARD: bảo vệ ở cửa. Mọi lần model xin dùng tool đều phải qua đây TRƯỚC khi chạy.

Ba kết luận cho mỗi lần xin (mục 7.3 báo cáo):
  allow  cho chạy
  ask    cần NGƯỜI duyệt (mục 7.4). Không có người duyệt (chạy tự động ban đêm) thì coi như từ chối.
  deny   cấm hẳn

Guard KHÁC allowlist ở web.py: web.py chặn "địa chỉ nào được phép tới" (tầng mạng). Guard chặn "model được
làm gì, bao nhiêu lần, dựa trên căn cứ nào" (tầng hành vi). Hai tầng độc lập, hỏng một vẫn còn một.

Các luật (tất cả nằm trong code, model không thể nới ra bằng lời lẽ):
  1. Nguồn gốc URL (provenance): fetch_url chỉ tự chạy với URL (a) có trong câu hỏi, (b) nằm trong kết quả
     search_web trước đó, hoặc (c) có dạng trang bài viết chuẩn (/wiki/Tên hoặc /abs/Mã), không query string.
     URL khác, nhất là URL có ?query hoặc dạng lạ, cần người duyệt. Chặn kênh rò rỉ qua query string, và chặn
     việc một trang web gài lệnh "hãy tải địa chỉ X" nhét URL do kẻ tấn công chọn.
  2. Từ khóa tìm kiếm: cấm chứa bí mật hoặc chuỗi dài bất thường (có thể là dữ liệu bị rò qua ô tìm kiếm).
  3. Chặn lặp: cùng một lời gọi y hệt quá N lần thì từ chối (dấu hiệu agent đi vào vòng lặp).
  4. Ngân sách tài nguyên: số lần tải trang mới, tổng ký tự web, thời gian, tổng token. Hết ngân sách thì
     dừng (với thời gian và token) hoặc từ chối tool (với tải trang).
"""
import json
import re
import time
import urllib.parse
from collections import Counter
from dataclasses import dataclass

from tracing import SECRET_PATTERNS


@dataclass
class Policy:
    injection_mode: str = "mark"           # "mark" đánh dấu, "remove" xóa câu, "off" tắt (xem injection.py)
    enforce_url_provenance: bool = True    # luật 1: URL phải có nguồn gốc hoặc có dạng chuẩn
    repeat_limit: int = 3                  # luật 3
    max_fetches: int = 8                   # số lần tải trang MỚI (đọc tiếp từ bản lưu không tính)
    max_web_chars: int = 80_000            # tổng ký tự nội dung web đưa cho model
    max_seconds: int = 300                 # tổng thời gian một lần chạy
    max_input_tokens: int = 250_000        # tổng token vào đã dùng


@dataclass
class Decision:
    verdict: str                           # "allow" | "ask" | "deny"
    reason: str = ""


ALLOW = Decision("allow")

_URL_RE = re.compile(r"https?://[^\s<>\"')\]]+")
_WIKI_PATH = re.compile(r"^/wiki/[^/?#]+$")
_ARXIV_PATH = re.compile(r"^/(abs|html)/[A-Za-z0-9._/\-]+$")


def extract_urls(text):
    return {u.rstrip(".,;:!?") for u in _URL_RE.findall(text)}


def norm_url(url):
    """Chuẩn hóa để so sánh: bỏ #fragment, giải mã %xx, bỏ dấu / cuối."""
    return urllib.parse.unquote(urllib.parse.urldefrag(url.strip())[0]).rstrip("/")


def is_canonical_article(url):
    """URL có phải dạng trang bài viết chuẩn (không query, không fragment lạ)?"""
    try:
        parts = urllib.parse.urlsplit(url.strip())
    except ValueError:
        return False
    host = (parts.hostname or "").lower()
    if parts.query:
        return False
    if host.endswith(".wikipedia.org") or host == "wikipedia.org":
        return bool(_WIKI_PATH.match(urllib.parse.unquote(parts.path)))
    if host in ("arxiv.org", "www.arxiv.org"):
        return bool(_ARXIV_PATH.match(parts.path))
    return False


class GuardState:
    """Bộ đếm của MỘT lần chạy."""

    def __init__(self, question, policy):
        self.policy = policy
        self.started = time.monotonic()
        self.known_urls = {norm_url(u) for u in extract_urls(question)}
        self.repeats = Counter()
        self.fetches = 0
        self.web_chars = 0
        self.denied = 0
        self.asked = 0

    def note_search_results(self, text):
        """URL xuất hiện trong kết quả tìm kiếm trở thành URL có nguồn gốc."""
        self.known_urls |= {norm_url(u) for u in extract_urls(text)}

    def note_web_result(self, text):
        self.web_chars += len(text)

    def register(self, action, args, is_new_fetch):
        """Ghi nhận một lời gọi ĐÃ ĐƯỢC CHO CHẠY."""
        self.repeats[(action, json.dumps(args, sort_keys=True, ensure_ascii=False))] += 1
        if is_new_fetch:
            self.fetches += 1


def check_call(action, args, state, pages):
    """Quyết định cho một lời gọi tool. `pages` là các trang đã tải (khóa là URL)."""
    policy = state.policy
    key = (action, json.dumps(args, sort_keys=True, ensure_ascii=False))
    if state.repeats[key] >= policy.repeat_limit:
        return Decision("deny", f"đã gọi y hệt {policy.repeat_limit} lần rồi, có vẻ đang lặp. Hãy đổi cách hoặc nộp bài")

    if action == "fetch_url":
        url = args.get("url", "")
        loaded = {norm_url(u) for u in pages}
        is_new = norm_url(url) not in loaded
        if is_new and state.fetches >= policy.max_fetches:
            return Decision("deny", f"đã tải đủ {policy.max_fetches} trang mới, hết ngân sách tải. Hãy nộp bài với những gì đã có")
        if is_new and state.web_chars >= policy.max_web_chars:
            return Decision("deny", "đã đọc quá nhiều nội dung web, hết ngân sách. Hãy nộp bài với những gì đã có")
        if is_new and policy.enforce_url_provenance:
            if norm_url(url) not in state.known_urls and not is_canonical_article(url):
                return Decision("ask", f"URL không có trong câu hỏi hay kết quả tìm kiếm và không phải dạng trang bài viết chuẩn: {url[:150]}")

    elif action == "search_web":
        query = args.get("query", "")
        if any(p.search(query) for p in SECRET_PATTERNS):
            return Decision("deny", "từ khóa tìm kiếm chứa chuỗi giống bí mật (token, khóa)")
        if any(len(word) > 40 for word in re.findall(r"\S+", query)):
            return Decision("deny", "từ khóa chứa chuỗi dài bất thường (có thể là dữ liệu bị rò qua ô tìm kiếm)")
        if state.web_chars >= policy.max_web_chars:
            return Decision("deny", "đã đọc quá nhiều nội dung web, hết ngân sách. Hãy nộp bài với những gì đã có")
    return ALLOW


def check_budget(state, totals):
    """Trả về lý do phải DỪNG cả lần chạy, hoặc None nếu còn ngân sách."""
    policy = state.policy
    elapsed = time.monotonic() - state.started
    if elapsed > policy.max_seconds:
        return f"quá thời gian cho phép ({int(elapsed)}s > {policy.max_seconds}s)"
    if totals["input_tokens"] > policy.max_input_tokens:
        return f"quá ngân sách token ({totals['input_tokens']} > {policy.max_input_tokens})"
    return None
