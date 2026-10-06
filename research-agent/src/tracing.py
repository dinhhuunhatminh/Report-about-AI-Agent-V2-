"""Khối TRACE: camera ghi lại từng bước của mỗi lần chạy.

Mỗi lần chạy có một mã (run_id) và một thư mục riêng: research-agent/runs/<run_id>/
  trace.jsonl   mỗi sự kiện MỘT dòng JSON (định dạng JSON Lines): máy lọc và đếm được
  answer.md     câu trả lời cuối kèm kết quả kiểm tra trích dẫn, để người đọc

Các sự kiện: run_start, llm_call, tool_call, citation_check, llm_error, run_end.
Bí mật (token, khóa) bị che trước khi ghi, vì log thường được chia sẻ và lưu lâu.
"""
import json
import re
import secrets
from datetime import datetime
from pathlib import Path

RUNS_DIR = Path(__file__).resolve().parents[1] / "runs"

SECRET_PATTERNS = [re.compile(p) for p in (
    r"ghp_[A-Za-z0-9]{20,}",
    r"github_pat_[A-Za-z0-9_]{20,}",
    r"sk-ant-[A-Za-z0-9_\-]{10,}",
    r"AKIA[0-9A-Z]{16}",
    r"(?i)bearer\s+[A-Za-z0-9._\-]{16,}",
)]


def redact(obj):
    """Che bí mật trong mọi chuỗi (kể cả chuỗi lồng trong dict, list)."""
    if isinstance(obj, str):
        for pattern in SECRET_PATTERNS:
            obj = pattern.sub("[ĐÃ CHE]", obj)
        return obj
    if isinstance(obj, dict):
        return {k: redact(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact(v) for v in obj]
    return obj


class Trace:
    def __init__(self, runs_dir=RUNS_DIR):
        self.run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2)
        self.dir = Path(runs_dir) / self.run_id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "trace.jsonl"

    def log(self, event, **data):
        record = {"ts": datetime.now().isoformat(timespec="milliseconds"),
                  "run": self.run_id, "event": event, **data}
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(redact(record), ensure_ascii=False) + "\n")

    def write_answer(self, text):
        (self.dir / "answer.md").write_text(redact(text), encoding="utf-8")


def read_trace(path):
    """Đọc lại file trace.jsonl thành danh sách dict."""
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def render_answer_md(question, result):
    """Dựng nội dung answer.md từ kết quả một lần chạy."""
    lines = [f"# {question}", "", f"Trạng thái: **{result['status']}**", ""]
    if result.get("answer"):
        lines += ["## Trả lời", "", result["answer"], "", "## Trích dẫn", ""]
        verified = {i: c for i, c in enumerate((result.get("verification") or {}).get("citations", []))}
        if not result["citations"]:
            lines.append("(không có)")
        for i, c in enumerate(result["citations"]):
            status = verified.get(i, {}).get("status", "chưa kiểm tra")
            mark = "ĐẠT" if status == "ok" else f"KHÔNG ĐẠT ({status})"
            lines.append(f'- [{c["doc_id"]}] "{c["quote"]}" -> {mark}')
    totals = result.get("totals", {})
    lines += ["", "## Thống kê", "",
              f"- Bước: {result.get('steps')}, lần gọi LLM: {totals.get('llm_calls')}",
              f"- Token vào/ra: {totals.get('input_tokens')}/{totals.get('output_tokens')}",
              f"- Thời gian gọi LLM: {totals.get('llm_ms', 0) / 1000:.1f}s, quy đổi ~{totals.get('cost_usd', 0):.3f} USD",
              f"- Model: {result.get('model')}"]
    return "\n".join(lines) + "\n"
