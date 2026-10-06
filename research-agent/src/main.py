"""Điểm vào: python src/main.py "câu hỏi" [--max-steps N] [--model tên]

Lưu ý hiển thị tiếng Việt trên Windows PowerShell: chạy `chcp 65001` trước nếu chữ bị lỗi.
"""
import argparse
import sys

from agent import DEFAULT_BUDGET_CHARS, run_agent
from guard import Policy
from memory import LongTerm


def ask_human(action, args, reason):
    """Người duyệt: guard nghi ngờ một hành động và hỏi bạn. Không trả lời được (không có bàn phím) thì từ chối."""
    print(f"\n[GUARD HỎI] {reason}\n  hành động: {action} {args}")
    try:
        return input("  Cho phép? [y/N] ").strip().lower() in ("y", "yes", "có", "co")
    except EOFError:
        return False


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Agent tra cứu kho tài liệu (giai đoạn 1)")
    parser.add_argument("question", help="Câu hỏi cần tra cứu")
    parser.add_argument("--max-steps", type=int, default=8, help="Số bước tối đa (mặc định 8)")
    parser.add_argument("--model", default=None, help="Tên model (mặc định: model của tài khoản)")
    parser.add_argument("--no-memory", action="store_true", help="Không đọc/ghi trí nhớ dài hạn")
    parser.add_argument("--ask", action="store_true",
                        help="Hỏi bạn trước khi chạy hành động guard nghi ngờ (mặc định: tự động từ chối)")
    parser.add_argument("--injection", choices=["mark", "remove", "off"], default="mark",
                        help="Xử lý câu nghi chứa lệnh gài trong nội dung web: mark (đánh dấu, mặc định), "
                             "remove (xóa câu), off (không làm gì)")
    parser.add_argument("--no-defense", action="store_true",
                        help="TẮT cách ly injection và luật nguồn URL. Chỉ để thử nghiệm so sánh, đừng dùng khi chạy thật")
    parser.add_argument("--budget", type=int, default=DEFAULT_BUDGET_CHARS,
                        help="Chỉ cắt gọn lịch sử khi tổng kết quả tool vượt số ký tự này (0 = không bao giờ cắt)")
    args = parser.parse_args()

    print(f"CÂU HỎI: {args.question}\n")
    memory = None if args.no_memory else LongTerm()
    budget = args.budget if args.budget > 0 else None
    policy = Policy(injection_mode="off" if args.no_defense else args.injection, enforce_url_provenance=not args.no_defense)
    result = run_agent(args.question, max_steps=args.max_steps, model=args.model, memory=memory,
                       budget_chars=budget, policy=policy, approver=ask_human if args.ask else None)

    print("\n" + "=" * 60)
    print(f"TRẠNG THÁI: {result['status']}")
    if result["answer"]:
        print(f"\nTRẢ LỜI:\n{result['answer']}")
        print("\nTRÍCH DẪN (đã kiểm tra bằng code):")
        statuses = [c["status"] for c in (result.get("verification") or {}).get("citations", [])]
        for i, c in enumerate(result["citations"]):
            status = statuses[i] if i < len(statuses) else "?"
            mark = "ĐẠT" if status == "ok" else f"KHÔNG ĐẠT ({status})"
            print(f'  [{c["doc_id"]}] {mark}\n      "{c["quote"]}"')
        if not result["citations"]:
            print("  (không có)")
    if result.get("web_pages"):
        print("\nTRANG WEB ĐÃ TẢI:")
        for url in result["web_pages"]:
            print(f"  {url}")
    notes = result.get("notes", [])
    if notes:
        print(f"\nGHI CHÚ NGẮN HẠN: {len(notes)} ghi chú đã lưu")
    if memory is not None:
        print(f"TRÍ NHỚ DÀI HẠN: gợi ý đọc lại {result['recalled']}; "
              f"đã ghi thêm {result.get('memory_added')}; tổng {memory.stats()}")
    g = result.get("guard", {})
    if g.get("denied") or g.get("asked") or g.get("injection_sentences_flagged") or result.get("error"):
        print(f"\nGUARD: chặn {g.get('denied', 0)}, hỏi người {g.get('asked', 0)} (duyệt {g.get('approved', 0)}), "
              f"phát hiện {g.get('injection_sentences_flagged', 0)} câu nghi chứa chỉ thị"
              + (f"; DỪNG vì {result['error']}" if result["status"] == "budget_exceeded" else ""))
    print(f"\nTRACE: {result['trace_path']}")
    t = result["totals"]
    print(f"\nTHỐNG KÊ: {result['steps']} bước, {t['llm_calls']} lần gọi LLM, "
          f"{t['input_tokens']} token vào, {t['output_tokens']} token ra, "
          f"{t['llm_ms'] / 1000:.1f}s, quy đổi ~{t['cost_usd']:.3f} USD, model {result['model']}")
    return 0 if result["status"] == "finished" else 1


if __name__ == "__main__":
    sys.exit(main())
