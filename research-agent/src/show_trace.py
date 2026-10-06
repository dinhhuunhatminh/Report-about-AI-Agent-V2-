"""Xem lại trace của một lần chạy dưới dạng bảng dễ đọc.

Dùng:  python research-agent/src/show_trace.py            (lần chạy mới nhất)
       python research-agent/src/show_trace.py <run_id>   (một lần chạy cụ thể)
"""
import sys

from tracing import RUNS_DIR, read_trace


def find_run(arg):
    if arg:
        return RUNS_DIR / arg / "trace.jsonl"
    runs = sorted(p for p in RUNS_DIR.glob("*") if (p / "trace.jsonl").exists())
    if not runs:
        raise SystemExit("Chưa có lần chạy nào trong research-agent/runs/")
    return runs[-1] / "trace.jsonl"


def short(value, width):
    text = str(value).replace("\n", " ")
    return text if len(text) <= width else text[:width - 1] + "…"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    path = find_run(sys.argv[1] if len(sys.argv) > 1 else None)
    events = read_trace(path)
    print(f"Trace: {path}\n")
    print(f"{'bước':<5}{'sự kiện':<17}{'chi tiết':<62}{'ms':>7}{'token vào':>11}")
    print("-" * 102)
    for e in events:
        kind, step = e["event"], e.get("step", "")
        if kind == "run_start":
            print(f"{'':<5}{kind:<17}{short(e['question'], 62):<62}")
        elif kind == "llm_call":
            print(f"{step:<5}{kind:<17}{short(e['action'] + ' ' + str(e['args']), 60):<62}{e['ms']:>7}{e['input_tokens']:>11}  prompt {e.get('prompt_chars', '?')} ký tự")
        elif kind == "tool_call":
            print(f"{step:<5}{kind:<17}{short(('OK ' if e['ok'] else 'LỖI ') + e['action'] + ', ' + str(e['result_chars']) + ' ký tự', 60):<62}{e['ms']:>7}")
        elif kind == "citation_check":
            ok = sum(c["status"] == "ok" for c in e["citations"])
            detail = "lần %d: %d/%d đạt" % (e["attempt"], ok, len(e["citations"]))
            if e["problems"]:
                detail += " | " + "; ".join(e["problems"])
            print(f"{step:<5}{kind:<17}{short(detail, 60):<62}")
        elif kind == "guard":
            detail = "%s %s: %s" % (e["verdict"].upper(), e["action"], e["reason"])
            print(f"{step:<5}{kind:<17}{short(detail, 60):<62}")
        elif kind == "injection_found":
            rules = ", ".join(sorted({f["rule"] for f in e["findings"]}))
            print(f"{step:<5}{kind:<17}{short('%s: %d câu: %s' % (e.get('mode', '?'), e['count'], rules), 60):<62}")
        elif kind == "budget_exceeded":
            print(f"{step:<5}{kind:<17}{short(e['reason'], 60):<62}")
        elif kind == "memory_recall":
            recalled = {k: e[k] for k in ("similar", "facts", "lessons", "stale_skipped")}
            print(f"{'':<5}{kind:<17}{short('đọc lại: ' + str(recalled), 60):<62}")
        elif kind == "memory_write":
            detail = "ghi: %d fact, %d bài học | tổng %s" % (e["facts"], e["lessons"], e["stats"])
            print(f"{'':<5}{kind:<17}{short(detail, 60):<62}")
        elif kind == "llm_error":
            print(f"{step:<5}{kind:<17}{short(e['error'], 60):<62}")
        elif kind == "run_end":
            t = e["totals"]
            print("-" * 102)
            print(f"Kết thúc: {e['status']} | {e['steps']} bước | {t['llm_calls']} lần gọi LLM | "
                  f"{t['input_tokens']} token vào, {t['output_tokens']} ra | {t['llm_ms'] / 1000:.1f}s | ~{t['cost_usd']:.3f} USD")


if __name__ == "__main__":
    main()
