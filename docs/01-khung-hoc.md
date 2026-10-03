# Khung học: AI Agent CI/CD

Mục tiêu: hiểu cách tạo, kết nối và điều khiển một AI agent, thông qua bài test
"tự động commit code lên GitHub theo lịch và deploy".

## Lộ trình

| Bước | Chủ đề | Câu hỏi cần trả lời | Làm ở đâu trong project |
|---|---|---|---|
| 1 | Cách tạo agent | Vòng lặp agent là gì (input → LLM → tool → kết quả → lặp)? | `run-agent.ps1` gọi `claude -p` |
| 2 | Cách kết nối | Agent xác thực với LLM và GitHub bằng gì? | `claude login`, biến môi trường `GITHUB_PAT` |
| 3 | Memory | Ngắn hạn vs dài hạn khác nhau thế nào? Lưu ở đâu? | `CLAUDE.md`, `state.json` |
| 4 | Rule / xử lý input | Giới hạn hành vi và làm sạch dữ liệu đầu vào ra sao? | `CLAUDE.md`, `--allowedTools`, script bọc |
| 5 | Agent ↔ MCP | MCP server là gì, agent gọi tool qua MCP như thế nào? | `.mcp.json` |
| 6 | Thực thi trên thiết bị | Cho agent chạy lệnh nhưng vẫn an toàn bằng cách nào? | allowlist tool, nhánh riêng, log |
| 7 | Test | Quy trình tự động chạy đúng lịch, push, deploy? | Task Scheduler / GitHub Actions |

## Ghi chú nhanh

- Lịch chạy do scheduler (Task Scheduler / cron / GitHub Actions) đảm nhiệm, không phải LLM.
- LLM chỉ quyết định: commit gì, viết message ra sao, có deploy hay không.
- Quyền tối thiểu: token GitHub fine-grained, chỉ một repo.
- Có điểm dừng: giới hạn số bước (`--max-turns`) và xác nhận trước khi deploy production.

## Việc cần chốt (điền dần)

- [ ] Repo GitHub đích: ...
- [ ] Lịch chạy: ...
- [ ] Đích deploy: ...
