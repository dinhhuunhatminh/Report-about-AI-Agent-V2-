# ResearchAI-AGENT

Thư mục học về AI agent, chỉ dùng Claude qua gói Pro (Claude Code CLI), không dùng API key.

```
ResearchAI-AGENT/
├─ cicd-agent/        Project 1 (xong): agent commit + push + deploy theo lịch, dùng `claude -p`
├─ research-agent/    Project 2 (đang làm): agent tra cứu và tổng hợp, tự viết vòng lặp
├─ docs/              Báo cáo HTML, nguồn của trang GitHub Pages (phải nằm ở docs/)
└─ README.md
```

| Thư mục | Vai trò | Cách chạy |
|---|---|---|
| `cicd-agent/` | Lịch 01:40 mỗi ngày: phát hiện thay đổi, Claude commit và push vào `main`, kiểm tra deploy | Task Scheduler gọi `cicd-agent/run-agent.ps1` |
| `research-agent/` | Nhận câu hỏi, tìm nguồn, đọc, đối chiếu, trả lời có trích dẫn kiểm chứng | Xem `research-agent/README.md` |
| `docs/` | Báo cáo về agent, được GitHub Pages deploy | Tự động sau mỗi lần push |

Lưu ý: `cicd-agent/` tự commit mọi thay đổi trong toàn bộ repo này lúc 01:40, nên mọi file sửa trong ngày sẽ được đẩy lên GitHub (repo công khai).
