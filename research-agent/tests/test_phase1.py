"""Kiểm thử giai đoạn 1: không gọi LLM, chỉ kiểm tra phần code (schema, tool, kho tài liệu).

Chạy: python -m unittest discover -s research-agent/tests -v
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from prompts import build_system_prompt, build_user_prompt  # noqa: E402
from schema import validate  # noqa: E402
from tools import CONTEXT_TOOLS, FINISH_TOOL, REGISTRY, run_tool  # noqa: E402
from tools import corpus  # noqa: E402


class SchemaTests(unittest.TestCase):
    schema = REGISTRY["search_corpus"].input_schema

    def test_valid(self):
        self.assertEqual(validate({"query": "memory", "limit": 3}, self.schema), [])

    def test_missing_required(self):
        self.assertTrue(any("thiếu" in e for e in validate({}, self.schema)))

    def test_wrong_type(self):
        self.assertTrue(validate({"query": 123}, self.schema))

    def test_bool_is_not_integer(self):
        self.assertTrue(validate({"query": "ab", "limit": True}, self.schema))

    def test_out_of_range(self):
        self.assertTrue(validate({"query": "ab", "limit": 99}, self.schema))

    def test_extra_param_rejected(self):
        self.assertTrue(any("không có trong khai báo" in e for e in validate({"query": "ab", "x": 1}, self.schema)))

    def test_finish_citation_needs_quote(self):
        bad = {"answer": "a", "citations": [{"doc_id": "01"}]}
        self.assertTrue(validate(bad, FINISH_TOOL["input_schema"]))


class CorpusTests(unittest.TestCase):
    def test_search_finds_right_document(self):
        self.assertIn("04-memory", corpus.search_corpus("embedding từ khóa").splitlines()[0])

    def test_search_ignores_accents_and_case(self):
        self.assertEqual(corpus.search_corpus("VÒNG LẶP").splitlines()[0],
                         corpus.search_corpus("vong lap").splitlines()[0])

    def test_search_no_match(self):
        self.assertIn("Không có tài liệu", corpus.search_corpus("zzzzqqq"))

    def test_read_document_paginates(self):
        first = corpus.read_document("05-an-toan")
        self.assertIn("ký tự 0-", first)

    def test_read_unknown_document(self):
        self.assertIn("LỖI", corpus.read_document("khong-co"))

    def test_path_traversal_cannot_read_files(self):
        out = corpus.read_document("../../README")
        self.assertIn("LỖI", out)
        self.assertNotIn("ResearchAI-AGENT", out)


class RunToolTests(unittest.TestCase):
    def test_unknown_tool(self):
        ok, text = run_tool("rm_rf", {})
        self.assertFalse(ok)
        self.assertIn("search_corpus", text)

    def test_bad_args_return_error_not_crash(self):
        ok, text = run_tool("read_document", {"start": "x"})
        self.assertFalse(ok)
        self.assertIn("LỖI THAM SỐ", text)

    def test_ok(self):
        ok, text = run_tool("search_corpus", {"query": "memory"})
        self.assertTrue(ok)


class PromptTests(unittest.TestCase):
    def test_system_prompt_lists_all_tools(self):
        prompt = build_system_prompt(REGISTRY, CONTEXT_TOOLS)
        for name in list(REGISTRY) + ["save_note", "finish"]:
            self.assertIn(name, prompt)

    def test_last_step_forces_finish(self):
        self.assertIn("BƯỚC CUỐI", build_user_prompt("q", [], 1))


if __name__ == "__main__":
    unittest.main()
