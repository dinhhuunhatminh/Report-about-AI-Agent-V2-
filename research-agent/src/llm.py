"""Khối LLM: gọi `claude -p` như một HÀM. Đưa văn bản vào, nhận lại JSON đúng khuôn.

Claude không tự làm gì ở đây: nó chỉ trả về một quyết định dạng JSON. Mọi việc khác
(vòng lặp, chạy tool, memory, kiểm tra) là code Python của mình.

Các cờ dưới đây giúp mỗi lần gọi nhẹ (~1.000 token thay vì hơn 58.000) mà vẫn dùng đăng nhập Claude Pro:
  --tools ""                  tắt mọi công cụ của Claude Code (để Claude không tự hành động)
  --system-prompt             rule do mình viết, thay thế system prompt mặc định
  --json-schema               buộc đầu ra theo khuôn, kết quả nằm ở trường structured_output
  --safe-mode                 tắt CLAUDE.md, skill, plugin, MCP... (không nạp ngữ cảnh thừa)
  --strict-mcp-config, --disable-slash-commands   tắt thêm MCP và skill
  --no-session-persistence    không lưu phiên
Không dùng được --bare vì nó chỉ nhận API key.
"""
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

# Chạy ở một thư mục rỗng để Claude Code không nạp nhầm CLAUDE.md của repo.
NEUTRAL_DIR = Path(tempfile.gettempdir()) / "research-agent-neutral"


class LLMError(Exception):
    """Gọi Claude thất bại (lỗi tiến trình, hết giờ, đầu ra không đúng khuôn)."""


def _claude_command():
    """Trả về lệnh gọi claude. Trên Windows gọi thẳng claude.exe để tránh lỗi nháy kép của cmd.exe."""
    override = os.environ.get("CLAUDE_BIN")
    if override:
        return [override]
    found = shutil.which("claude")
    if not found:
        raise LLMError("Không tìm thấy lệnh 'claude'. Cài Claude Code CLI hoặc đặt biến CLAUDE_BIN.")
    exe = Path(found).parent / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
    return [str(exe)] if exe.exists() else [found]


def ask(system_prompt, user_prompt, schema, model=None, timeout=180):
    """Hỏi Claude một lần. Trả về dict:
         decision                          JSON Claude trả về (đúng theo schema)
         input_tokens, output_tokens       số token (input gồm cả phần cache)
         cost_usd                          chi phí quy đổi theo giá API (gói Pro không bị tính tiền này)
         ms, model                         thời gian và tên model đã trả lời
    Ném LLMError nếu thất bại.
    """
    cmd = _claude_command() + [
        "-p",
        "--tools", "",
        "--system-prompt", system_prompt,
        "--json-schema", json.dumps(schema),
        "--output-format", "json",
        "--no-session-persistence",
        "--safe-mode", "--strict-mcp-config", "--disable-slash-commands",
    ]
    if model:
        cmd += ["--model", model]

    NEUTRAL_DIR.mkdir(parents=True, exist_ok=True)
    started = time.time()
    try:
        # Nội dung hỏi đi qua stdin: không bị giới hạn độ dài dòng lệnh, không lỗi xuống dòng.
        proc = subprocess.run(
            cmd, input=user_prompt, cwd=NEUTRAL_DIR, capture_output=True,
            text=True, encoding="utf-8", timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise LLMError(f"Claude không trả lời sau {timeout} giây")
    except OSError as exc:
        raise LLMError(f"Không chạy được claude: {exc}")

    if proc.returncode != 0:
        raise LLMError(f"claude thoát với mã {proc.returncode}: {proc.stderr.strip()[:300] or proc.stdout.strip()[:300]}")

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise LLMError(f"Đầu ra không phải JSON: {proc.stdout[:300]!r}")

    if data.get("is_error"):
        raise LLMError(f"Claude báo lỗi: {str(data.get('result'))[:300]}")
    decision = data.get("structured_output")
    if not isinstance(decision, dict):
        raise LLMError(f"Không có structured_output; result={str(data.get('result'))[:300]!r}")

    usage = data.get("usage", {})
    models = list((data.get("modelUsage") or {}).keys())
    return {
        "decision": decision,
        "input_tokens": usage.get("input_tokens", 0) + usage.get("cache_creation_input_tokens", 0)
                        + usage.get("cache_read_input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
        "cost_usd": data.get("total_cost_usd", 0.0),
        "ms": int((time.time() - started) * 1000),
        "model": models[0] if models else "?",
    }
