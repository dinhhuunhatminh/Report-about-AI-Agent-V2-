"""Kiểm thử giai đoạn 3: memory ngắn hạn, dài hạn và các rủi ro của memory. Dùng LLM giả.

Chạy: python -m unittest discover -s research-agent/tests -v
"""
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import agent  # noqa: E402
from memory import LESSON_TEXTS, MAX_LESSONS_KEPT, MAX_NOTES, PLACEHOLDER, LongTerm, ShortTerm, compact_history  # noqa: E402
from tools.corpus import load_corpus  # noqa: E402
from tracing import Trace  # noqa: E402

DOC = "01-vong-lap-agent"
REAL_QUOTE = "Với agent nhỏ, giới hạn khuyến nghị là 15 bước mỗi lần chạy."
DOC2 = "04-memory"
QUOTE2 = "Với agent nhỏ, nên bắt đầu bằng file và tìm theo từ khóa"
Q1 = "Giới hạn số bước khuyến nghị cho agent nhỏ là bao nhiêu?"
Q1_SIMILAR = "Cho agent nhỏ thì giới hạn số bước khuyến nghị là gì?"


def entry(step, action, ok=True, result="x" * 50, args=None):
    return {"step": step, "action": action, "args": args or {}, "ok": ok, "result": result}


def fake_reply(action, args, thought="t"):
    return {"decision": {"thought": thought, "action": action, "args": args},
            "input_tokens": 100, "output_tokens": 10, "cost_usd": 0.001, "ms": 5, "model": "fake"}


def finished_result(citations=None, status="finished", kinds=()):
    citations = citations if citations is not None else [{"doc_id": DOC, "quote": REAL_QUOTE}]
    return {"status": status, "steps": 3, "citations": citations, "totals": {"cost_usd": 0.01},
            "verification": {"ok": status == "finished",
                             "citations": [dict(c, status="ok") for c in citations]},
            "check_failure_kinds": set(kinds)}


class ShortTermTests(unittest.TestCase):
    def test_add_duplicate_and_full(self):
        st = ShortTerm()
        self.assertEqual(st.add(DOC, REAL_QUOTE), "saved")
        self.assertEqual(st.add(DOC, REAL_QUOTE), "duplicate")
        for i in range(MAX_NOTES - 1):
            st.add(DOC, f"đoạn trích khác số {i}")
        self.assertEqual(st.add(DOC, "đoạn vượt quá giới hạn"), "full")
        self.assertIn("[1]", st.render())

    def test_compact_none_keeps_everything(self):
        hist = [entry(i, "read_document") for i in range(1, 5)]
        self.assertEqual(compact_history(hist, None), hist)

    def test_no_compaction_while_under_budget(self):
        hist = [entry(i, "read_document", result="y" * 100) for i in range(1, 5)]
        self.assertEqual(compact_history(hist, budget_chars=1000), hist)

    def make_history(self):
        return [
            entry(1, "search_corpus", result="- 01-vong-lap-agent | A | điểm 3\n    ...\n- 04-memory | B | điểm 2\n    ..."),
            entry(2, "read_document", result="NỘI DUNG DÀI " * 50),
            entry(3, "read_document", ok=False, result="LỖI " + "y" * 400),
            entry(4, "read_document", result="GẦN ĐÂY 4" * 20),
            entry(5, "read_document", result="GẦN ĐÂY 5" * 20),
        ]

    def test_over_budget_shrinks_oldest_first_and_keeps_last(self):
        hist = self.make_history()
        view = compact_history(hist, budget_chars=500)
        self.assertIn("01-vong-lap-agent, 04-memory", view[0]["result"])
        self.assertEqual(view[1]["result"], PLACEHOLDER)
        self.assertLessEqual(len(view[2]["result"]), 150)
        self.assertEqual(view[4]["result"], hist[4]["result"])          # bước cuối luôn nguyên vẹn
        self.assertIn("NỘI DUNG DÀI", hist[1]["result"])                # lịch sử gốc không bị đổi

    def test_stops_shrinking_as_soon_as_budget_is_met(self):
        hist = self.make_history()
        total = sum(len(e["result"]) for e in hist)
        # ngân sách chỉ cần bỏ bớt bước 1 (kết quả search) là đủ -> các bước sau giữ nguyên
        saved_by_step1 = len(hist[0]["result"]) - len(compact_history(hist, 0)[0]["result"])
        view = compact_history(hist, budget_chars=total - saved_by_step1)
        self.assertNotEqual(view[0]["result"], hist[0]["result"])
        self.assertEqual(view[1]["result"], hist[1]["result"])


class LongTermTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ltm = LongTerm(Path(self.tmp.name) / "m.db")

    def tearDown(self):
        self.tmp.cleanup()

    def test_record_then_recall_similar_question(self):
        added = self.ltm.record_run("r1", Q1, finished_result())
        self.assertEqual(added["facts"], 1)
        recall = self.ltm.recall(Q1_SIMILAR)
        self.assertEqual(len(recall["similar"]), 1)
        self.assertEqual(recall["similar"][0]["docs"], DOC)
        self.assertEqual(recall["facts"][0]["quote"], REAL_QUOTE)
        self.assertIn("TRÍ NHỚ TỪ CÁC LẦN TRƯỚC", self.ltm.render_recall(recall))

    def test_unrelated_question_recalls_nothing(self):
        self.ltm.record_run("r1", Q1, finished_result())
        recall = self.ltm.recall("Giá gói Claude Max là bao nhiêu mỗi tháng?")
        self.assertEqual((recall["similar"], recall["facts"]), ([], []))
        self.assertEqual(self.ltm.render_recall(recall), "")

    def test_failed_run_stores_no_facts_and_is_not_recalled_as_similar(self):
        added = self.ltm.record_run("r1", Q1, finished_result(status="citation_failed"))
        self.assertEqual(added["facts"], 0)
        self.assertEqual(self.ltm.recall(Q1_SIMILAR)["similar"], [])

    def test_only_verified_citations_become_facts(self):
        res = finished_result([{"doc_id": DOC, "quote": REAL_QUOTE}, {"doc_id": DOC, "quote": "câu bịa đặt chưa kiểm chứng"}])
        res["verification"]["citations"][1]["status"] = "not_in_document"
        res["verification"]["ok"] = True      # dù cờ tổng bị sai, từng fact vẫn phải tự đạt
        self.assertEqual(self.ltm.record_run("r1", Q1, res)["facts"], 1)

    def test_duplicate_facts_not_stored_twice(self):
        self.ltm.record_run("r1", Q1, finished_result())
        self.assertEqual(self.ltm.record_run("r2", Q1_SIMILAR, finished_result())["facts"], 0)
        self.assertEqual(self.ltm.stats()["facts"], 1)

    def test_stale_fact_is_skipped(self):
        """Tài liệu đã đổi nên quote không còn nguyên văn: fact lỗi thời phải bị bỏ qua."""
        self.ltm.record_run("r1", Q1, finished_result())
        with sqlite3.connect(self.ltm.path) as db:
            db.execute("INSERT INTO facts(ts,run_id,doc_id,quote) VALUES ('t','r0',?,?)",
                       (DOC, "Giới hạn khuyến nghị cho agent nhỏ từng là 99 bước mỗi lần chạy."))
        recall = self.ltm.recall(Q1_SIMILAR)
        self.assertEqual([f["quote"] for f in recall["facts"]], [REAL_QUOTE])
        self.assertEqual(recall["stale_skipped"], 1)

    def test_secrets_are_redacted_before_storing(self):
        question = "Thử với token ghp_" + "A" * 30 + " giới hạn số bước agent"
        self.ltm.record_run("r1", question, finished_result())
        stored = self.ltm.dump()["runs"][0][4]
        self.assertNotIn("ghp_AAAA", stored)

    def test_lessons_come_from_fixed_templates(self):
        added = self.ltm.record_run("r1", Q1, finished_result(status="citation_failed", kinds={"not_in_document"}))
        self.assertEqual(added["lessons"], 1)
        self.assertEqual(self.ltm.dump()["lessons"][0][2], LESSON_TEXTS["not_in_document"])
        self.assertEqual(self.ltm.record_run("r2", Q1, finished_result(status="citation_failed", kinds={"not_in_document"}))["lessons"], 0)

    def test_lessons_capped(self):
        with sqlite3.connect(self.ltm.path) as db:
            for i in range(MAX_LESSONS_KEPT + 10):
                db.execute("INSERT INTO lessons(ts,run_id,kind,text) VALUES ('t','r',?,?)", (f"k{i}", f"bài học {i}"))
        self.ltm.record_run("r1", Q1, finished_result())
        self.assertEqual(self.ltm.stats()["lessons"], MAX_LESSONS_KEPT)

    def test_forget_and_clear(self):
        self.ltm.record_run("r1", Q1, finished_result())
        self.ltm.record_run("r2", "Một câu hỏi khác về memory của agent", finished_result([{"doc_id": DOC2, "quote": QUOTE2}]))
        self.ltm.forget("r1")
        self.assertEqual(self.ltm.stats(), {"runs": 1, "facts": 1, "lessons": 0})
        self.ltm.clear()
        self.assertEqual(self.ltm.stats(), {"runs": 0, "facts": 0, "lessons": 0})


def scripted(replies, prompts):
    it = iter(replies)

    def fn(system, user, schema, model=None, timeout=180):
        prompts.append(user)
        return next(it)
    return fn


class AgentMemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ltm = LongTerm(Path(self.tmp.name) / "m.db")

    def tearDown(self):
        self.tmp.cleanup()

    def run_agent(self, question, replies, memory="default", max_steps=8, budget_chars=agent.DEFAULT_BUDGET_CHARS):
        prompts = []
        memory = self.ltm if memory == "default" else memory
        with mock.patch.object(agent.llm, "ask", side_effect=scripted(replies, prompts)):
            result = agent.run_agent(question, max_steps=max_steps, emit=lambda *_: None,
                                     trace=Trace(Path(self.tmp.name) / "runs"), memory=memory, budget_chars=budget_chars)
        return result, prompts

    def good_run(self):
        return self.run_agent(Q1, [
            fake_reply("read_document", {"doc_id": DOC}),
            fake_reply("finish", {"answer": "15 bước", "citations": [{"doc_id": DOC, "quote": REAL_QUOTE}]}),
        ])

    def test_second_run_receives_recall_in_prompt(self):
        first, first_prompts = self.good_run()
        self.assertEqual(first["status"], "finished")
        self.assertNotIn("TRÍ NHỚ", first_prompts[0])
        self.assertEqual(first["memory_added"]["facts"], 1)

        second, second_prompts = self.run_agent(Q1_SIMILAR, [
            fake_reply("read_document", {"doc_id": DOC}),
            fake_reply("finish", {"answer": "15 bước", "citations": [{"doc_id": DOC, "quote": REAL_QUOTE}]}),
        ])
        self.assertEqual(second["recalled"]["facts"], 1)
        self.assertIn("TRÍ NHỚ TỪ CÁC LẦN TRƯỚC", second_prompts[0])
        self.assertIn(DOC, second_prompts[0])

    def test_recall_cannot_be_used_as_citation_source(self):
        """Trí nhớ chỉ là gợi ý: dù có quote trong trí nhớ, chưa đọc tài liệu thì trích dẫn vẫn bị từ chối."""
        self.good_run()
        cheat = fake_reply("finish", {"answer": "15 bước", "citations": [{"doc_id": DOC, "quote": REAL_QUOTE}]})
        result, prompts = self.run_agent(Q1_SIMILAR, [cheat, cheat, cheat])
        self.assertIn(REAL_QUOTE, prompts[0])                  # trí nhớ có hiện trong prompt...
        self.assertEqual(result["status"], "citation_failed")   # ...nhưng không được chấp nhận làm nguồn
        self.assertEqual(result["verification"]["citations"][0]["status"], "not_seen")

    def test_failed_run_creates_lesson_not_fact(self):
        bad = fake_reply("finish", {"answer": "x", "citations": [{"doc_id": DOC, "quote": "câu bịa không có trong tài liệu"}]})
        result, _ = self.run_agent(Q1, [fake_reply("read_document", {"doc_id": DOC}), bad, bad, bad])
        self.assertEqual(result["status"], "citation_failed")
        stats = self.ltm.stats()
        self.assertEqual((stats["facts"], stats["lessons"]), (0, 1))

    def test_memory_none_means_no_recall_and_no_db(self):
        result, prompts = self.run_agent(Q1, [
            fake_reply("read_document", {"doc_id": DOC}),
            fake_reply("finish", {"answer": "15", "citations": [{"doc_id": DOC, "quote": REAL_QUOTE}]}),
        ], memory=None)
        self.assertNotIn("memory_added", result)
        self.assertEqual(self.ltm.stats()["runs"], 0)


class AgentShortTermTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def run_agent(self, replies, **kw):
        prompts = []
        with mock.patch.object(agent.llm, "ask", side_effect=scripted(replies, prompts)):
            result = agent.run_agent("câu hỏi thử", emit=lambda *_: None,
                                     trace=Trace(Path(self.tmp.name)), memory=None, **kw)
        return result, prompts

    def test_save_note_ok_then_visible_in_next_prompt(self):
        result, prompts = self.run_agent([
            fake_reply("read_document", {"doc_id": DOC}),
            fake_reply("save_note", {"doc_id": DOC, "quote": REAL_QUOTE}),
            fake_reply("finish", {"answer": "15", "citations": [{"doc_id": DOC, "quote": REAL_QUOTE}]}),
        ])
        self.assertEqual(result["status"], "finished")
        self.assertEqual(len(result["notes"]), 1)
        self.assertIn(f'[1] ({DOC}) "{REAL_QUOTE}"', prompts[2])

    def test_save_note_rejects_paraphrase(self):
        result, _ = self.run_agent([
            fake_reply("read_document", {"doc_id": DOC}),
            fake_reply("save_note", {"doc_id": DOC, "quote": "Agent nhỏ nên có tối đa mười lăm bước"}),
            fake_reply("finish", {"answer": "Không tìm thấy trong tài liệu.", "citations": []}),
        ])
        self.assertEqual(result["notes"], [])
        self.assertFalse(result["history"][1]["ok"])
        self.assertIn("KHÔNG LƯU", result["history"][1]["result"])

    def test_save_note_rejects_unread_document(self):
        result, _ = self.run_agent([
            fake_reply("save_note", {"doc_id": DOC, "quote": REAL_QUOTE}),
            fake_reply("finish", {"answer": "Không tìm thấy trong tài liệu.", "citations": []}),
        ])
        self.assertEqual(result["notes"], [])
        self.assertIn("chưa đọc", result["history"][0]["result"])

    def test_old_results_are_compacted_when_over_budget(self):
        unique = "Điều kiện dừng có hai loại"    # đoạn chữ chỉ có ở tài liệu 01
        replies = [fake_reply("read_document", {"doc_id": DOC}),
                   fake_reply("read_document", {"doc_id": DOC2}),
                   fake_reply("read_document", {"doc_id": "03-mcp"}),
                   fake_reply("read_document", {"doc_id": "05-an-toan"}),
                   fake_reply("finish", {"answer": "Không tìm thấy trong tài liệu.", "citations": []})]
        _, prompts = self.run_agent(list(replies), budget_chars=1500)
        self.assertIn(unique, prompts[1])          # bước 2: còn trong ngân sách, tài liệu 01 nguyên vẹn
        self.assertNotIn(unique, prompts[4])       # bước 5: đã bị lược bớt
        self.assertIn(PLACEHOLDER, prompts[4])

    def test_no_compaction_when_budget_is_none(self):
        unique = "Điều kiện dừng có hai loại"
        replies = [fake_reply("read_document", {"doc_id": DOC}),
                   fake_reply("read_document", {"doc_id": DOC2}),
                   fake_reply("read_document", {"doc_id": "03-mcp"}),
                   fake_reply("read_document", {"doc_id": "05-an-toan"}),
                   fake_reply("finish", {"answer": "Không tìm thấy trong tài liệu.", "citations": []})]
        _, prompts = self.run_agent(list(replies), budget_chars=None)
        self.assertIn(unique, prompts[4])
        self.assertNotIn(PLACEHOLDER, prompts[4])


if __name__ == "__main__":
    unittest.main()
