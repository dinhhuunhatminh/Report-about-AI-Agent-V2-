"""Khối MEMORY: sổ tay hôm nay (ngắn hạn) + tủ hồ sơ lâu dài (dài hạn).

NGẮN HẠN (trong một lần chạy)
  - ShortTerm.notes     ghi chú agent chủ động lưu bằng tool save_note (mỗi ghi chú là một trích dẫn
                        đã được code kiểm tra). Ghi chú LUÔN được đưa vào prompt.
  - compact_history()   cắt gọn lịch sử: kết quả tool cũ bị thay bằng một dòng "(đã lược bớt)".
                        Nhờ vậy prompt không phình dần; thông tin quan trọng đã nằm trong ghi chú.

DÀI HẠN (giữa các lần chạy), lưu bằng SQLite trong research-agent/memory/memory.db
  - runs      mỗi lần chạy: câu hỏi, trạng thái, số bước, chi phí
  - facts     các trích dẫn ĐÃ ĐƯỢC KIỂM TRA ĐẠT từ những lần chạy thành công
  - lessons   bài học sinh ra từ lỗi (nộp trích dẫn sai...), lấy từ CÂU MẪU CÓ SẴN trong code

Khi bắt đầu một lần chạy, agent ĐỌC LẠI trí nhớ liên quan và nhận nó như gợi ý định hướng.

Ba rủi ro của memory (mục 5 báo cáo) và cách chặn ở đây:
  1. Memory lỗi thời   -> mỗi fact được kiểm tra lại với kho tài liệu hiện tại; không còn nguyên văn thì bỏ.
  2. Memory bị đầu độc -> chỉ ghi thứ đã kiểm chứng (fact đạt, lần chạy thành công); bài học dùng câu mẫu
                          cố định chứ không chép chữ do model sinh ra; trí nhớ KHÔNG BAO GIỜ được tính là
                          "đã đọc" nên không thể dùng làm nguồn trích dẫn (xem verify.py).
  3. Lộ thông tin nhạy cảm -> che bí mật trước khi ghi; có lệnh xem, quên một lần chạy, xóa sạch.

Lệnh quản lý:  python research-agent/src/memory.py show | forget <run_id> | clear
"""
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from tools.corpus import STOPWORDS, fold, load_corpus
from tracing import redact

DB_PATH = Path(__file__).resolve().parents[1] / "memory" / "memory.db"
MAX_NOTES = 12
MAX_LESSONS_KEPT = 30
MIN_OVERLAP = 2           # số từ khóa tối thiểu phải trùng để coi là "liên quan"
MIN_RATIO = 0.4           # và phải trùng ít nhất 40% từ khóa của bên ngắn hơn (tránh khớp vì vài từ chung)
# Từ để hỏi quá chung (đã bỏ dấu): "bao nhiêu", "nào"... xuất hiện ở mọi câu hỏi nên không có giá trị phân biệt.
QUESTION_WORDS = {"bao", "nhieu", "nao", "sao", "dau", "may", "khac"}
PLACEHOLDER = "(đã lược bớt để tiết kiệm ngữ cảnh; cần xem lại thì gọi lại công cụ)"

# Bài học tạo từ CÂU MẪU theo loại lỗi, không chép nội dung do model sinh ra (chống đầu độc memory).
LESSON_TEXTS = {
    "not_in_document": "Có lần nộp trích dẫn không nằm nguyên văn trong tài liệu. Phải copy chính xác, không diễn đạt lại hay dịch.",
    "not_seen": "Có lần trích dẫn đoạn chưa đọc trong lần chạy đó. Phải đọc tài liệu bằng read_document trước khi trích dẫn.",
    "unknown_doc": "Có lần dùng mã tài liệu không tồn tại. Chỉ dùng doc_id lấy từ kết quả tìm kiếm.",
    "no_citation": "Có lần trả lời không có trích dẫn. Không có trích dẫn thì phải nói rõ là không tìm thấy trong tài liệu.",
}


def _tokens(text):
    return {t for t in re.findall(r"\w+", fold(text))
            if len(t) >= 3 and t not in STOPWORDS and t not in QUESTION_WORDS}


def _related(a, b):
    """Hai tập từ khóa có liên quan không: trùng đủ nhiều VÀ đủ tỉ lệ so với bên ngắn hơn."""
    overlap = len(a & b)
    return overlap >= MIN_OVERLAP and overlap / max(1, min(len(a), len(b))) >= MIN_RATIO, overlap


# --------------------------------------------------------------------------- ngắn hạn

class ShortTerm:
    """Ghi chú của lần chạy hiện tại."""

    def __init__(self):
        self.notes = []

    def add(self, doc_id, quote):
        """Trả về 'saved', 'duplicate' hoặc 'full'."""
        if any(n["doc_id"] == doc_id and n["quote"] == quote for n in self.notes):
            return "duplicate"
        if len(self.notes) >= MAX_NOTES:
            return "full"
        self.notes.append({"doc_id": doc_id, "quote": quote})
        return "saved"

    def render(self):
        return "\n".join(f'[{i}] ({n["doc_id"]}) "{n["quote"]}"' for i, n in enumerate(self.notes, start=1))


def _shrink(entry):
    """Rút gọn kết quả của một bước cũ."""
    entry = dict(entry)
    if entry["ok"] and entry["action"] == "search_corpus":
        ids = re.findall(r"^- (\S+) \|", entry["result"], flags=re.M)
        entry["result"] = f"(đã lược bớt; tài liệu khớp: {', '.join(ids) or 'không có'})"
    elif entry["ok"] and entry["action"] == "search_web":
        urls = re.findall(r"\| (https?://\S+) \|", entry["result"])
        entry["result"] = f"(đã lược bớt; kết quả web: {', '.join(urls[:5]) or 'không có'})"
    elif entry["ok"] and entry["action"] in ("read_document", "fetch_url"):
        entry["result"] = PLACEHOLDER
    elif not entry["ok"]:
        entry["result"] = entry["result"][:150]
    return entry


def compact_history(history, budget_chars, keep_last=1):
    """Trả về BẢN XEM của lịch sử để đưa vào prompt (lịch sử gốc không bị đổi).

    Chỉ cắt khi tổng độ dài các kết quả VƯỢT `budget_chars`. Khi đó rút gọn từ bước CŨ NHẤT trở đi,
    dừng ngay khi đã đủ ngân sách, và luôn giữ nguyên `keep_last` bước gần nhất.
    budget_chars=None nghĩa là không bao giờ cắt.

    Vì sao không cắt cố định N bước cũ: đã thử trên tài liệu ngắn, cắt luôn làm agent quên nội dung vừa đọc,
    đọc lại nhiều lần và tốn token gấp đôi (xem README research-agent). Cắt chỉ có lợi khi ngữ cảnh thật sự dài.
    """
    if budget_chars is None:
        return history
    total = sum(len(e["result"]) for e in history)
    if total <= budget_chars:
        return history
    view = list(history)
    for i in range(max(0, len(view) - keep_last)):
        if total <= budget_chars:
            break
        shrunk = _shrink(view[i])
        total -= len(view[i]["result"]) - len(shrunk["result"])
        view[i] = shrunk
    return view


# --------------------------------------------------------------------------- dài hạn

class LongTerm:
    def __init__(self, path=DB_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS runs(
                    run_id TEXT PRIMARY KEY, ts TEXT, question TEXT, status TEXT,
                    steps INTEGER, cost_usd REAL, docs TEXT);
                CREATE TABLE IF NOT EXISTS facts(
                    id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, run_id TEXT,
                    doc_id TEXT, quote TEXT, UNIQUE(doc_id, quote));
                CREATE TABLE IF NOT EXISTS lessons(
                    id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, run_id TEXT, kind TEXT UNIQUE, text TEXT);
            """)

    def _db(self):
        return _Conn(self.path)

    # ---- ghi
    def record_run(self, run_id, question, result):
        """Ghi một lần chạy. Chỉ ghi fact khi lần chạy thành công VÀ trích dẫn đã đạt kiểm tra."""
        now = datetime.now().isoformat(timespec="seconds")
        corpus = load_corpus()
        # CHỈ nhớ nguồn thuộc kho nội bộ. Nội dung web do người lạ viết và không kiểm tra lại được khi đọc lại
        # (không biết trang đã đổi chưa), nên không cho vào trí nhớ dài hạn: đóng đường đầu độc memory từ web.
        docs = sorted({c["doc_id"] for c in result.get("citations", []) if c["doc_id"] in corpus})
        added = {"facts": 0, "lessons": 0}
        with self._db() as db:
            db.execute("INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?,?,?)",
                       (run_id, now, redact(question)[:500], result["status"], result["steps"],
                        result.get("totals", {}).get("cost_usd", 0.0), ",".join(docs)))
            verification = result.get("verification") or {}
            if result["status"] == "finished" and verification.get("ok"):
                for c in verification["citations"]:
                    if c["status"] == "ok" and c["doc_id"] in corpus:
                        cur = db.execute("INSERT OR IGNORE INTO facts(ts,run_id,doc_id,quote) VALUES (?,?,?,?)",
                                         (now, run_id, c["doc_id"], redact(c["quote"])[:600]))
                        added["facts"] += cur.rowcount
            for kind in sorted(result.get("check_failure_kinds", [])):
                cur = db.execute("INSERT OR IGNORE INTO lessons(ts,run_id,kind,text) VALUES (?,?,?,?)",
                                 (now, run_id, kind, LESSON_TEXTS[kind]))
                added["lessons"] += cur.rowcount
            db.execute("DELETE FROM lessons WHERE id NOT IN (SELECT id FROM lessons ORDER BY id DESC LIMIT ?)",
                       (MAX_LESSONS_KEPT,))
        return added

    # ---- đọc lại
    def recall(self, question, limit=3):
        """Tìm trí nhớ liên quan tới câu hỏi mới. Trả về dict similar, facts, lessons, stale_skipped."""
        q_tokens = _tokens(question)
        docs = load_corpus()
        out = {"similar": [], "facts": [], "lessons": [], "stale_skipped": 0}
        with self._db() as db:
            for row in db.execute("SELECT run_id, question, docs FROM runs WHERE status='finished' ORDER BY ts DESC"):
                related, overlap = _related(q_tokens, _tokens(row[1]))
                if related:
                    out["similar"].append((overlap, {"run_id": row[0], "question": row[1], "docs": row[2]}))
            scored = []
            for doc_id, quote in db.execute("SELECT doc_id, quote FROM facts"):
                overlap = len(q_tokens & _tokens(quote))
                if overlap >= MIN_OVERLAP and overlap / max(1, len(q_tokens)) >= MIN_RATIO:
                    scored.append((overlap, doc_id, quote))
            out["lessons"] = [r[0] for r in db.execute("SELECT text FROM lessons ORDER BY id DESC LIMIT ?", (limit,))]

        out["similar"] = [x[1] for x in sorted(out["similar"], key=lambda x: -x[0])[:limit]]
        for overlap, doc_id, quote in sorted(scored, key=lambda x: -x[0]):
            if len(out["facts"]) >= limit:
                break
            if doc_id in docs and _norm(quote) in _norm(docs[doc_id]["text"]):
                out["facts"].append({"doc_id": doc_id, "quote": quote})
            else:
                out["stale_skipped"] += 1      # tài liệu đã đổi: fact lỗi thời, bỏ qua
        return out

    @staticmethod
    def render_recall(recall):
        """Dựng đoạn văn bản đưa vào prompt. Rỗng nếu không có gì liên quan."""
        if not (recall["similar"] or recall["facts"] or recall["lessons"]):
            return ""
        lines = ["TRÍ NHỚ TỪ CÁC LẦN TRƯỚC (chỉ là GỢI Ý định hướng, có thể lỗi thời; không phải nguồn trích dẫn):"]
        for s in recall["similar"]:
            lines.append(f'- Đã từng trả lời câu hỏi tương tự "{s["question"]}" bằng các tài liệu: {s["docs"] or "(không có)"}')
        for f in recall["facts"]:
            lines.append(f'- Trích dẫn đã từng được kiểm chứng ở [{f["doc_id"]}]: "{f["quote"]}"')
        for text in recall["lessons"]:
            lines.append(f"- Bài học: {text}")
        return "\n".join(lines)

    # ---- quản lý
    def stats(self):
        with self._db() as db:
            return {t: db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("runs", "facts", "lessons")}

    def forget(self, run_id):
        with self._db() as db:
            for table in ("facts", "lessons", "runs"):
                db.execute(f"DELETE FROM {table} WHERE run_id=?", (run_id,))

    def clear(self):
        with self._db() as db:
            for table in ("facts", "lessons", "runs"):
                db.execute(f"DELETE FROM {table}")

    def dump(self):
        with self._db() as db:
            return {
                "runs": db.execute("SELECT run_id, ts, status, steps, question FROM runs ORDER BY ts DESC").fetchall(),
                "facts": db.execute("SELECT run_id, doc_id, quote FROM facts ORDER BY id DESC").fetchall(),
                "lessons": db.execute("SELECT run_id, kind, text FROM lessons ORDER BY id DESC").fetchall(),
            }


class _Conn:
    """Mở kết nối, tự commit khi xong và LUÔN đóng (tránh khóa file trên Windows)."""

    def __init__(self, path):
        self.conn = sqlite3.connect(path)

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.conn.commit()
        self.conn.close()


def _norm(text):
    return re.sub(r"\s+", " ", text).strip().casefold()


def _cli():
    sys.stdout.reconfigure(encoding="utf-8")
    cmd = sys.argv[1] if len(sys.argv) > 1 else "show"
    ltm = LongTerm()
    if cmd == "show":
        data = ltm.dump()
        print(f"Đường dẫn: {ltm.path}\nThống kê: {ltm.stats()}\n")
        for run_id, ts, status, steps, question in data["runs"]:
            print(f"[run] {run_id} | {ts} | {status} | {steps} bước | {question}")
        for run_id, doc_id, quote in data["facts"]:
            print(f'[fact] ({doc_id}, từ {run_id}) "{quote[:110]}"')
        for run_id, kind, text in data["lessons"]:
            print(f"[bài học] ({kind}) {text}")
    elif cmd == "forget" and len(sys.argv) > 2:
        ltm.forget(sys.argv[2])
        print(f"Đã quên lần chạy {sys.argv[2]}. Thống kê: {ltm.stats()}")
    elif cmd == "clear":
        ltm.clear()
        print(f"Đã xóa sạch trí nhớ dài hạn. Thống kê: {ltm.stats()}")
    else:
        print("Dùng: python research-agent/src/memory.py show | forget <run_id> | clear")


if __name__ == "__main__":
    _cli()
