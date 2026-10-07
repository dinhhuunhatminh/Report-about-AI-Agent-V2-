"""CHẠY BỘ EVAL: mỗi bài chạy N lần với LLM thật, chấm bằng code, báo tỉ lệ đạt kèm khoảng tin cậy.

Chạy:
  python research-agent/evals/run_evals.py                          # toàn bộ, mỗi bài 3 lần
  python research-agent/evals/run_evals.py --repeat 5 --category unanswerable conflict
  python research-agent/evals/run_evals.py --only corpus_buoc web_helios
  python research-agent/evals/run_evals.py --model claude-haiku-4-5-20251001
  python research-agent/evals/run_evals.py --compare research-agent/evals/results/eval_<model>_<giờ>.json

Mỗi lần chạy lưu research-agent/evals/results/eval_<model>_<giờ>.json (đầy đủ từng lần chạy) và .md (báo cáo).
Agent chạy ở cấu hình mặc định (không có trí nhớ dài hạn để các lần chạy độc lập nhau, không có người duyệt).
"""
import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import agent  # noqa: E402
import graders  # noqa: E402
from cases import CASES  # noqa: E402
from fixtures import FixtureWeb  # noqa: E402
from guard import Policy  # noqa: E402
from tracing import Trace  # noqa: E402

RESULTS_DIR = Path(__file__).resolve().parent / "results"
CATEGORY_NAMES = {
    "answerable_corpus": "Có đáp án (kho nội bộ)", "answerable_web": "Có đáp án (web)",
    "unanswerable": "Không có đáp án", "conflict": "Hai nguồn mâu thuẫn", "injection": "Trang chứa lệnh gài",
}


INFRA_RETRIES = 2      # số lần thử lại khi lỗi hạ tầng (không tính lần đầu)
INFRA_WAIT = 20        # giây chờ giữa các lần thử lại


def run_case(case, web_env, model, trace_root, max_steps=8, retries=INFRA_RETRIES, wait=INFRA_WAIT):
    """Chạy một bài MỘT lần và chấm. Web luôn là web giả (fixtures).

    LỖI HẠ TẦNG KHÔNG PHẢI LỖI CỦA AGENT. Trong một lần chạy thật, Claude Code tự cập nhật giữa chừng và lệnh `claude`
    biến mất vài phút, làm 21 lần chạy hỏng ngay lập tức; nếu tính chúng là "agent trả lời sai" thì phép đo vô nghĩa.
    Vì vậy: gặp status "llm_error" thì chờ rồi thử lại; nếu vẫn lỗi sau khi hết lượt thử thì đánh dấu invalid=True
    và LOẠI khỏi mọi tỉ lệ (báo cáo vẫn liệt kê riêng để không bị giấu).
    """
    started = time.time()
    attempts = 0
    while True:
        attempts += 1
        with web_env.patched():
            result = agent.run_agent(case["question"], max_steps=max_steps, emit=lambda *_: None, memory=None,
                                     model=model, policy=Policy(), approver=None, trace=Trace(trace_root))
            requests = list(web_env.requests)
        if result["status"] != "llm_error" or attempts > retries:
            break
        time.sleep(wait)
    checks = graders.grade(case, result, requests)
    totals = result["totals"]
    return {
        "case": case["id"], "category": case["category"], "model": result["model"],
        "passed": graders.passed(checks), "checks": checks, "status": result["status"], "steps": result["steps"],
        "invalid": result["status"] == "llm_error", "attempts": attempts, "error": result.get("error", ""),
        "input_tokens": totals["input_tokens"], "cost_usd": round(totals["cost_usd"], 4),
        "seconds": round(time.time() - started, 1), "answer": (result.get("answer") or "")[:600],
        "citations": graders.cited_docs(result), "trace": result["trace_path"],
    }


def valid(runs):
    """Các lần chạy hợp lệ (loại những lần hỏng vì hạ tầng)."""
    return [r for r in runs if not r.get("invalid")]


def rate(runs):
    runs = valid(runs)
    k, n = sum(r["passed"] for r in runs), len(runs)
    lo, hi = graders.wilson(k, n)
    return k, n, lo, hi


def render_report(runs, meta):
    cases = {c["id"]: c for c in CASES}
    good, bad_infra = valid(runs), [r for r in runs if r.get("invalid")]
    lines = ["# Kết quả eval research-agent", "",
             f"Model: `{meta['model']}` | {meta['repeat']} lần mỗi bài | {len(good)} lần chạy hợp lệ | bắt đầu {meta['started']} | "
             f"web: GIẢ (fixtures), chấm: bằng code", ""]
    if bad_infra:
        lines += [f"**{len(bad_infra)} lần chạy không hợp lệ (lỗi hạ tầng, ví dụ không gọi được Claude) đã bị LOẠI khỏi mọi tỉ lệ**, "
                  "liệt kê ở cuối báo cáo.", ""]
    lines += ["Khoảng tin cậy 95% (Wilson) đi kèm tỉ lệ đạt. Với 3 lần chạy mỗi bài khoảng này RẤT rộng "
              "(0/3 và 3/3 đều chưa phân biệt chắc với 'thỉnh thoảng sai'), nên đọc theo từng loại (cộng dồn nhiều bài) "
              "hơn là theo từng bài.", "",
              "## Theo loại", "", "| Loại | Đạt | Tỉ lệ | Khoảng 95% | Bước TB | Token vào TB | Thời gian TB |", "|---|---|---|---|---|---|---|"]
    for cat in CATEGORY_NAMES:
        sel = [r for r in good if r["category"] == cat]
        if not sel:
            continue
        k, n, lo, hi = rate(sel)
        lines.append(f"| {CATEGORY_NAMES[cat]} | {k}/{n} | {k / n:.0%} | {lo:.0%} đến {hi:.0%} | "
                     f"{sum(r['steps'] for r in sel) / n:.1f} | {sum(r['input_tokens'] for r in sel) // n} | "
                     f"{sum(r['seconds'] for r in sel) / n:.0f}s |")
    if good:
        k, n, lo, hi = rate(good)
        lines.append(f"| **Tất cả** | **{k}/{n}** | **{k / n:.0%}** | {lo:.0%} đến {hi:.0%} | "
                     f"{sum(r['steps'] for r in good) / n:.1f} | {sum(r['input_tokens'] for r in good) // n} | "
                     f"{sum(r['seconds'] for r in good) / n:.0f}s |")
    lines += ["", "## Theo bài", "", "| Bài | Loại | Đạt | Kiểm tra hay hỏng nhất |", "|---|---|---|---|"]
    for cid in dict.fromkeys(r["case"] for r in runs):
        sel = [r for r in good if r["case"] == cid]
        infra = sum(1 for r in bad_infra if r["case"] == cid)
        fails = {}
        for r in sel:
            for c in r["checks"]:
                if not c["ok"]:
                    fails[c["name"]] = fails.get(c["name"], 0) + 1
        worst = "; ".join(f"{name} ({cnt}x)" for name, cnt in sorted(fails.items(), key=lambda x: -x[1])[:2]) or "-"
        k, n, _, _ = rate(sel) if sel else (0, 0, 0, 0)
        shown = f"{k}/{n}" + (f" (+{infra} lỗi hạ tầng)" if infra else "")
        lines.append(f"| {cid} | {CATEGORY_NAMES[cases[cid]['category']] if cid in cases else '?'} | {shown} | {worst} |")
    failed = [r for r in good if not r["passed"]]
    if failed:
        lines += ["", "## Các lần chạy không đạt (để chẩn đoán)", ""]
        for r in failed[:12]:
            why = "; ".join(f"{c['name']}" + (f" [{c['detail']}]" if c["detail"] else "") for c in r["checks"] if not c["ok"])
            lines.append(f"- `{r['case']}` ({r['steps']} bước): {why}\n  trả lời: {r['answer'][:200]!r}")
    if bad_infra:
        lines += ["", "## Các lần chạy không hợp lệ (lỗi hạ tầng, KHÔNG tính vào tỉ lệ)", ""]
        for r in bad_infra[:12]:
            lines.append(f"- `{r['case']}` sau {r.get('attempts', 1)} lần thử: {str(r.get('error', ''))[:160]}")
    return "\n".join(lines) + "\n"


def render_comparison(old_runs, new_runs):
    def by_case(runs):
        out = {}
        for r in valid(runs):
            out.setdefault(r["case"], []).append(r["passed"])
        return out
    old, new = by_case(old_runs), by_case(new_runs)
    lines = ["# So sánh với lần chạy trước", "",
             "| Bài | Trước | Nay | Ghi chú |", "|---|---|---|---|"]
    worse = 0
    for cid in new:
        n_k, n_n = sum(new[cid]), len(new[cid])
        if cid not in old:
            lines.append(f"| {cid} | (mới) | {n_k}/{n_n} | |")
            continue
        o_k, o_n = sum(old[cid]), len(old[cid])
        drop = n_k / n_n < o_k / o_n
        worse += drop
        lines.append(f"| {cid} | {o_k}/{o_n} | {n_k}/{n_n} | {'GIẢM, cần xem' if drop else ''} |")
    ok, on = sum(sum(v) for v in old.values()), sum(len(v) for v in old.values())
    nk, nn = sum(sum(v) for v in new.values()), sum(len(v) for v in new.values())
    lines += ["", f"Tổng: {ok}/{on} ({ok / max(on, 1):.0%}) -> {nk}/{nn} ({nk / max(nn, 1):.0%}). Số bài giảm: {worse}.",
              "Lưu ý: với vài lần chạy mỗi bài, mức giảm 1 lần có thể chỉ là biến động ngẫu nhiên của model."]
    return "\n".join(lines) + "\n"


def merge_runs(old_runs, new_runs):
    """Gộp kết quả: bài nào chạy lại thì thay toàn bộ các lần chạy cũ của bài đó, bài khác giữ nguyên."""
    rerun = {r["case"] for r in new_runs}
    return [r for r in old_runs if r["case"] not in rerun] + new_runs


def persist(new_runs, args, started):
    """Ghi file kết quả (.json và .md) từ các lần chạy đến lúc này. Gọi sau MỖI bài, ghi đè cùng một file.

    Trước đây chỉ ghi ở cuối; một lần phải dừng giữa chừng đã làm mất kết quả của các bài đã chạy xong.
    Có --merge thì gộp với file cũ (bài nào chạy lại thì thay bài đó).
    """
    meta = {"model": new_runs[0]["model"], "repeat": args.repeat, "started": started.strftime("%Y-%m-%d %H:%M")}
    runs = new_runs
    if args.merge:
        old = json.loads(Path(args.merge).read_text(encoding="utf-8"))
        runs = merge_runs(old["runs"], new_runs)
        meta = {**old["meta"], "merged_with": started.strftime("%Y-%m-%d %H:%M")}
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    base = RESULTS_DIR / f"eval_{meta['model']}_{started.strftime('%Y%m%d-%H%M')}"
    base.with_suffix(".json").write_text(json.dumps({"meta": meta, "runs": runs}, ensure_ascii=False, indent=2), encoding="utf-8")
    report = render_report(runs, meta)
    if args.compare:
        report += "\n" + render_comparison(json.loads(Path(args.compare).read_text(encoding="utf-8"))["runs"], runs)
    base.with_suffix(".md").write_text(report, encoding="utf-8")
    return {"json": base.with_suffix(".json"), "md": base.with_suffix(".md"), "report": report}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Chạy bộ eval của research-agent")
    parser.add_argument("--repeat", type=int, default=3, help="số lần chạy mỗi bài (mặc định 3)")
    parser.add_argument("--category", nargs="+", choices=list(CATEGORY_NAMES), help="chỉ chạy các loại này")
    parser.add_argument("--only", nargs="+", help="chỉ chạy các bài có id này")
    parser.add_argument("--model", default=None, help="tên model (mặc định: model của tài khoản)")
    parser.add_argument("--compare", metavar="FILE", help="so sánh với file kết quả trước")
    parser.add_argument("--merge", metavar="FILE", help="gộp kết quả vào file này (thay các bài vừa chạy lại), "
                                                         "dùng để chạy lại các bài bị lỗi hạ tầng")
    args = parser.parse_args()

    cases = [c for c in CASES if (not args.category or c["category"] in args.category) and (not args.only or c["id"] in args.only)]
    if not cases:
        raise SystemExit("Không có bài nào khớp bộ lọc.")
    web_env, runs, started = FixtureWeb(), [], datetime.now()
    for case in cases:
        results = []
        for i in range(args.repeat):
            row = run_case(case, web_env, args.model, ROOT / "runs", max_steps=case.get("max_steps", 8))
            row["run"] = i + 1
            results.append(row)
        runs += results
        saved = persist(runs, args, started)          # LƯU NGAY sau mỗi bài: dừng giữa chừng vẫn không mất dữ liệu
        ok_runs = valid(results)
        k = sum(r["passed"] for r in ok_runs)
        failed = sorted({c["name"] for r in ok_runs for c in r["checks"] if not c["ok"]})
        infra = len(results) - len(ok_runs)
        print(f"[{case['id']:<24} {CATEGORY_NAMES[case['category']]:<24}] đạt {k}/{len(ok_runs)} | "
              f"{sum(r['steps'] for r in results) / len(results):.1f} bước TB | "
              f"{sum(r['seconds'] for r in results) / len(results):.0f}s TB"
              + (f" | hỏng: {'; '.join(failed)}" if failed else "")
              + (f" | {infra} LẦN LỖI HẠ TẦNG (không tính)" if infra else ""), flush=True)

    print("\n" + saved["report"])
    print(f"Đã lưu: {saved['json']}")


if __name__ == "__main__":
    main()
