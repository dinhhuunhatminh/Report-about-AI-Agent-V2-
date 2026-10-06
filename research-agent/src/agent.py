"""Khối VÒNG LẶP: người quản lý điều phối. Hỏi LLM -> kiểm tra -> chạy tool -> ghi kết quả -> lặp.

Đây là bản "vòng lặp tự viết" tương ứng mục 2.4 của báo cáo, nhưng LLM được gọi qua `claude -p`
(llm.py) thay vì API, và quyết định của LLM là JSON thay vì khối tool_use.

Giai đoạn 2: ghi trace từng bước (tracing.py) và kiểm tra trích dẫn bằng code (verify.py).
Giai đoạn 3: memory (memory.py)
  - đầu lần chạy: đọc lại trí nhớ dài hạn liên quan, đưa vào prompt như gợi ý
  - trong lần chạy: ghi chú (save_note) + cắt gọn kết quả tool cũ để prompt không phình
  - cuối lần chạy: ghi vào trí nhớ dài hạn những gì ĐÃ ĐƯỢC KIỂM CHỨNG
"""
import time

import llm
import verify
from memory import ShortTerm, compact_history
from prompts import build_system_prompt, build_user_prompt
from schema import validate
from tools import CONTEXT_TOOLS, FINISH_TOOL, REGISTRY, SAVE_NOTE_TOOL, run_tool
from tools.corpus import load_corpus
from tracing import Trace, render_answer_md

MAX_RESULT_CHARS = 4000     # cắt kết quả tool để lịch sử không phình to
MAX_FINISH_ATTEMPTS = 3     # số lần được nộp bài; trích dẫn sai quá số này thì dừng và báo thất bại
DEFAULT_BUDGET_CHARS = 12000   # chỉ cắt gọn lịch sử khi tổng kết quả tool vượt ngưỡng này (ký tự)

# Khuôn của MỖI quyết định LLM: một hành động trong danh sách + tham số.
# Tham số cụ thể được kiểm tra riêng theo schema của từng tool.
DECISION_SCHEMA = {
    "type": "object",
    "properties": {
        "thought": {"type": "string"},
        "action": {"type": "string", "enum": list(REGISTRY) + [t["name"] for t in CONTEXT_TOOLS]},
        "args": {"type": "object"},
    },
    "required": ["thought", "action", "args"],
}


def run_agent(question, max_steps=8, model=None, emit=print, trace=None, memory=None, budget_chars=DEFAULT_BUDGET_CHARS):
    """Chạy agent cho một câu hỏi. Trả về dict kết quả (status, answer, citations, thống kê, run_id).

    memory:    một LongTerm (trí nhớ dài hạn) hoặc None để chạy không có trí nhớ dài hạn.
    budget_chars: chỉ cắt gọn lịch sử khi tổng kết quả tool vượt số ký tự này; None để không bao giờ cắt.
    """
    trace = trace or Trace()
    system_prompt = build_system_prompt(REGISTRY, CONTEXT_TOOLS)
    history = []
    short_term = ShortTerm()
    ctx = {"pages": {}}          # các trang web đã tải trong lần chạy này (nguyên văn), để kiểm tra trích dẫn

    def citable_docs():
        """Nguồn được phép trích dẫn: kho nội bộ + trang web đã tải trong lần chạy này."""
        return {**load_corpus(), **ctx["pages"]}

    finish_attempts = 0
    totals = {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "llm_calls": 0, "llm_ms": 0}
    result = {"status": "max_steps", "answer": None, "citations": [], "steps": 0, "model": "?",
              "run_id": trace.run_id, "trace_path": str(trace.path), "check_failure_kinds": set(),
              "recalled": {"similar": 0, "facts": 0, "lessons": 0, "stale_skipped": 0}}

    trace.log("run_start", question=question, max_steps=max_steps, model=model, budget_chars=budget_chars,
              long_term_memory=memory is not None, system_prompt_chars=len(system_prompt))

    # ---- ĐỌC LẠI trí nhớ dài hạn (một lần, đầu lần chạy)
    recall_text = ""
    if memory is not None:
        recall = memory.recall(question)
        recall_text = memory.render_recall(recall)
        result["recalled"] = {"similar": len(recall["similar"]), "facts": len(recall["facts"]),
                              "lessons": len(recall["lessons"]), "stale_skipped": recall["stale_skipped"]}
        trace.log("memory_recall", **result["recalled"], chars=len(recall_text))
        if recall_text:
            emit(f"[trí nhớ] gợi ý từ các lần trước: {result['recalled']}")

    for step in range(1, max_steps + 1):
        steps_left = max_steps - step + 1
        user_prompt = build_user_prompt(question, compact_history(history, budget_chars), steps_left,
                                        notes_text=short_term.render(), recall_text=recall_text)

        try:
            reply = llm.ask(system_prompt, user_prompt, DECISION_SCHEMA, model=model)
        except llm.LLMError as exc:
            emit(f"[bước {step}] LỖI LLM: {exc}")
            trace.log("llm_error", step=step, error=str(exc))
            result.update(status="llm_error", error=str(exc), steps=step)
            break

        totals["llm_calls"] += 1
        totals["input_tokens"] += reply["input_tokens"]
        totals["output_tokens"] += reply["output_tokens"]
        totals["cost_usd"] += reply["cost_usd"]
        totals["llm_ms"] += reply["ms"]
        result["model"] = reply["model"]

        decision = reply["decision"]
        action, args, thought = decision["action"], decision["args"], decision["thought"]
        trace.log("llm_call", step=step, model=reply["model"], ms=reply["ms"],
                  input_tokens=reply["input_tokens"], output_tokens=reply["output_tokens"],
                  cost_usd=reply["cost_usd"], prompt_chars=len(user_prompt),
                  thought=thought, action=action, args=args)
        emit(f"[bước {step}] {thought}")
        emit(f"          -> {action} {args}   ({reply['ms']} ms, {reply['input_tokens']} token vào)")
        result["steps"] = step

        tool_ms = 0
        if action == "finish":
            errors = validate(args, FINISH_TOOL["input_schema"])
            if errors:
                ok, text = False, "LỖI THAM SỐ: " + "; ".join(errors)
            else:
                finish_attempts += 1
                check = verify.check_finish(args, history, citable_docs())
                trace.log("citation_check", step=step, attempt=finish_attempts, ok=check["ok"],
                          citations=check["citations"], problems=check["problems"])
                for c in check["citations"]:
                    emit(f"          kiểm tra [{c['doc_id']}]: {'ĐẠT' if c['status'] == 'ok' else 'KHÔNG ĐẠT (' + c['status'] + ')'}")
                if check["ok"]:
                    result.update(status="finished", answer=args["answer"], citations=args["citations"],
                                  verification=check)
                    break
                result["check_failure_kinds"].update(check["kinds"])
                if finish_attempts >= MAX_FINISH_ATTEMPTS:
                    result.update(status="citation_failed", answer=args["answer"], citations=args["citations"],
                                  verification=check)
                    break
                ok, text = False, check["message"]
        elif action == "save_note":
            errors = validate(args, SAVE_NOTE_TOOL["input_schema"])
            if errors:
                ok, text = False, "LỖI THAM SỐ: " + "; ".join(errors)
            else:
                status = verify.check_quote(args["doc_id"], args["quote"], verify.seen_norm(history), citable_docs())
                if status != "ok":
                    ok, text = False, f"KHÔNG LƯU GHI CHÚ: {verify.explain(status)}"
                else:
                    outcome = short_term.add(args["doc_id"], args["quote"])
                    ok = outcome != "full"
                    text = {"saved": f"Đã lưu ghi chú #{len(short_term.notes)}.",
                            "duplicate": "Ghi chú này đã có rồi.",
                            "full": "KHÔNG LƯU: đã đủ số ghi chú tối đa."}[outcome]
        else:
            started = time.perf_counter()
            ok, text = run_tool(action, args, ctx)
            tool_ms = int((time.perf_counter() - started) * 1000)

        if len(text) > MAX_RESULT_CHARS:
            text = text[:MAX_RESULT_CHARS] + "\n...(đã cắt bớt)"
        trace.log("tool_call", step=step, action=action, args=args, ok=ok, ms=tool_ms,
                  result_chars=len(text), result_preview=text[:500])
        emit(f"          <- {'OK' if ok else 'LỖI'}: {text[:140].replace(chr(10), ' ')}{'...' if len(text) > 140 else ''}")
        history.append({"step": step, "action": action, "args": args, "ok": ok, "result": text})

    result["totals"] = totals
    result["history"] = history
    result["notes"] = list(short_term.notes)
    result["web_pages"] = sorted({p["url"] for p in ctx["pages"].values()})

    # ---- GHI trí nhớ dài hạn (cuối lần chạy; chỉ phần đã kiểm chứng, xem memory.record_run)
    if memory is not None:
        added = memory.record_run(trace.run_id, question, result)
        result["memory_added"] = added
        trace.log("memory_write", **added, stats=memory.stats())
        emit(f"[trí nhớ] đã ghi: {added['facts']} fact mới, {added['lessons']} bài học mới")

    result["check_failure_kinds"] = sorted(result["check_failure_kinds"])
    trace.log("run_end", status=result["status"], steps=result["steps"], totals=totals,
              answer=result["answer"], model=result["model"], notes=len(short_term.notes),
              web_pages=result["web_pages"])
    trace.write_answer(render_answer_md(question, result))
    return result
