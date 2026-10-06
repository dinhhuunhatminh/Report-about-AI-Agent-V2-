"""Kiểm thử giai đoạn 2: trace và kiểm tra trích dẫn. Không gọi LLM thật (dùng LLM giả).

Chạy: python -m unittest discover -s research-agent/tests -v
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import agent  # noqa: E402
import verify  # noqa: E402
from tools.corpus import load_corpus  # noqa: E402
from tracing import Trace, read_trace, redact  # noqa: E402

DOC = "01-vong-lap-agent"
REAL_QUOTE = "Với agent nhỏ, giới hạn khuyến nghị là 15 bước mỗi lần chạy."


def history_with(*texts):
    return [{"step": i + 1, "action": "read_document", "args": {}, "ok": True, "result": t}
            for i, t in enumerate(texts)]


class VerifyTests(unittest.TestCase):
    docs = load_corpus()

    def check(self, quote, seen, doc=DOC):
        return verify.check_quote(doc, quote, verify._norm(seen), self.docs)

    def test_exact_quote_ok(self):
        self.assertEqual(self.check(REAL_QUOTE, self.docs[DOC]["text"]), "ok")

    def test_ignores_whitespace_and_case(self):
        self.assertEqual(self.check("VỚI agent nhỏ,   giới hạn khuyến nghị\nlà 15 bước mỗi lần chạy.",
                                    self.docs[DOC]["text"]), "ok")

    def test_paraphrase_rejected(self):
        self.assertEqual(self.check("Agent nhỏ nên có tối đa 15 bước cho mỗi lượt", self.docs[DOC]["text"]),
                         "not_in_document")

    def test_wrong_document_rejected(self):
        self.assertEqual(self.check(REAL_QUOTE, self.docs[DOC]["text"], doc="04-memory"), "not_in_document")

    def test_unknown_document(self):
        self.assertEqual(self.check(REAL_QUOTE, "", doc="khong-co"), "unknown_doc")

    def test_quote_not_seen_by_agent(self):
        self.assertEqual(self.check(REAL_QUOTE, "agent chưa đọc gì liên quan"), "not_seen")

    def test_fragments_joined_by_ellipsis(self):
        quote = "Với agent nhỏ, giới hạn khuyến nghị là 15 bước ... một lỗi lặp đi lặp lại có thể chạy vô hạn"
        self.assertEqual(self.check(quote, self.docs[DOC]["text"]), "ok")

    def test_check_finish_all_ok(self):
        args = {"answer": "15 bước", "citations": [{"doc_id": DOC, "quote": REAL_QUOTE}]}
        res = verify.check_finish(args, history_with(self.docs[DOC]["text"]))
        self.assertTrue(res["ok"])

    def test_check_finish_one_bad_fails_all(self):
        args = {"answer": "x", "citations": [{"doc_id": DOC, "quote": REAL_QUOTE},
                                             {"doc_id": DOC, "quote": "một câu hoàn toàn bịa đặt ra"}]}
        res = verify.check_finish(args, history_with(self.docs[DOC]["text"]))
        self.assertFalse(res["ok"])
        self.assertEqual([c["status"] for c in res["citations"]], ["ok", "not_in_document"])
        self.assertIn("KIỂM TRA TRÍCH DẪN THẤT BẠI", res["message"])

    def test_failed_tool_results_do_not_count_as_seen(self):
        hist = [{"step": 1, "action": "read_document", "args": {}, "ok": False, "result": self.docs[DOC]["text"]}]
        args = {"answer": "x", "citations": [{"doc_id": DOC, "quote": REAL_QUOTE}]}
        self.assertFalse(verify.check_finish(args, hist)["ok"])

    def test_no_citations_requires_not_found_statement(self):
        bad = verify.check_finish({"answer": "Giá là 100 USD", "citations": []}, [])
        good = verify.check_finish({"answer": "Không tìm thấy trong tài liệu.", "citations": []}, [])
        self.assertFalse(bad["ok"])
        self.assertTrue(good["ok"])


class TraceTests(unittest.TestCase):
    def test_redact_masks_secrets_recursively(self):
        data = {"a": "token ghp_" + "A" * 30, "b": ["Bearer " + "x" * 30, {"c": "sk-ant-" + "y" * 20}], "d": 5}
        out = json.dumps(redact(data))
        self.assertNotIn("ghp_AAAA", out)
        self.assertNotIn("xxxxxxxx", out)
        self.assertNotIn("sk-ant-yyy", out)
        self.assertEqual(redact(data)["d"], 5)

    def test_trace_writes_valid_json_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = Trace(tmp)
            t.log("run_start", question="q")
            t.log("llm_call", step=1, args={"k": "v"})
            events = read_trace(t.path)
            self.assertEqual([e["event"] for e in events], ["run_start", "llm_call"])
            self.assertTrue(all(e["run"] == t.run_id for e in events))


def fake_reply(action, args, thought="t"):
    return {"decision": {"thought": thought, "action": action, "args": args},
            "input_tokens": 100, "output_tokens": 10, "cost_usd": 0.001, "ms": 5, "model": "fake"}


class AgentLoopTests(unittest.TestCase):
    """Chạy vòng lặp thật với LLM giả có kịch bản, để kiểm tra logic mà không tốn hạn mức."""

    def run_scripted(self, replies, max_steps=8):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(agent.llm, "ask", side_effect=replies):
            trace = Trace(tmp)
            result = agent.run_agent("câu hỏi thử", max_steps=max_steps, emit=lambda *_: None, trace=trace)
            events = read_trace(trace.path)
            answer_md = (trace.dir / "answer.md").read_text(encoding="utf-8")
        return result, events, answer_md

    def test_happy_path(self):
        result, events, answer_md = self.run_scripted([
            fake_reply("read_document", {"doc_id": DOC}),
            fake_reply("finish", {"answer": "15 bước", "citations": [{"doc_id": DOC, "quote": REAL_QUOTE}]}),
        ])
        self.assertEqual(result["status"], "finished")
        kinds = [e["event"] for e in events]
        self.assertEqual(kinds[0], "run_start")
        self.assertEqual(kinds[-1], "run_end")
        self.assertIn("citation_check", kinds)
        self.assertIn("ĐẠT", answer_md)

    def test_fabricated_quote_is_rejected_then_corrected(self):
        result, events, _ = self.run_scripted([
            fake_reply("read_document", {"doc_id": DOC}),
            fake_reply("finish", {"answer": "x", "citations": [{"doc_id": DOC, "quote": "câu bịa không có trong tài liệu"}]}),
            fake_reply("finish", {"answer": "15 bước", "citations": [{"doc_id": DOC, "quote": REAL_QUOTE}]}),
        ])
        self.assertEqual(result["status"], "finished")
        checks = [e for e in events if e["event"] == "citation_check"]
        self.assertEqual([c["ok"] for c in checks], [False, True])

    def test_gives_up_after_max_finish_attempts(self):
        bad = fake_reply("finish", {"answer": "x", "citations": [{"doc_id": DOC, "quote": "câu bịa không có trong tài liệu"}]})
        result, _, answer_md = self.run_scripted([bad, bad, bad, bad])
        self.assertEqual(result["status"], "citation_failed")
        self.assertIn("KHÔNG ĐẠT", answer_md)

    def test_max_steps_stops_loop(self):
        replies = [fake_reply("search_corpus", {"query": "memory"})] * 3
        result, events, _ = self.run_scripted(replies, max_steps=3)
        self.assertEqual(result["status"], "max_steps")
        self.assertEqual(events[-1]["event"], "run_end")

    def test_bad_tool_args_become_error_not_crash(self):
        result, events, _ = self.run_scripted([
            fake_reply("read_document", {"start": "x"}),
            fake_reply("finish", {"answer": "Không tìm thấy trong tài liệu.", "citations": []}),
        ])
        self.assertEqual(result["status"], "finished")
        tool_events = [e for e in events if e["event"] == "tool_call"]
        self.assertFalse(tool_events[0]["ok"])

    def test_llm_error_is_traced(self):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(agent.llm, "ask", side_effect=agent.llm.LLMError("hỏng")):
            trace = Trace(tmp)
            result = agent.run_agent("q", emit=lambda *_: None, trace=trace)
            events = read_trace(trace.path)
        self.assertEqual(result["status"], "llm_error")
        self.assertIn("llm_error", [e["event"] for e in events])


if __name__ == "__main__":
    unittest.main()
