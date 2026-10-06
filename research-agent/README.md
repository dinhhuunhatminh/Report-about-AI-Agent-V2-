# research-agent: agent tra cứu và tổng hợp

Nhận một câu hỏi, tự tìm nguồn, đọc, đối chiếu, rồi trả lời kèm trích dẫn mà code kiểm tra được.
LLM là Claude qua `claude -p` (gói Pro). Vòng lặp, tool, rule, memory, trace là code Python tự viết.

## Khung làm việc: 6 khối

```
                    Câu hỏi của bạn
                          │
                          ▼
   ┌──────────────────────────────────────────────┐
   │  1. VÒNG LẶP (agent.py)                       │
   │     hỏi LLM → nhận quyết định → chạy tool →   │
   │     ghi kết quả → lặp (tối đa N bước)         │
   └───┬─────────┬──────────┬──────────┬──────────┘
       │         │          │          │
       ▼         ▼          ▼          ▼
  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
  │2. LLM  │ │3. TOOL │ │4. MEMO │ │5. GUARD│
  │llm.py  │ │tools/  │ │memory  │ │guard.py│
  │        │ │        │ │.py     │ │        │
  │claude  │ │search  │ │ngắn hạn│ │quyền   │
  │ -p     │ │fetch   │ │dài hạn │ │chống   │
  │+schema │ │note    │ │(SQLite)│ │injection│
  │        │ │finish  │ │        │ │        │
  └────────┘ └────────┘ └────────┘ └────────┘
       └─────────┴──────────┴──────────┘
                          │ mỗi bước đều ghi
                          ▼
              ┌────────────────────────┐
              │ 6. TRACE (trace.py)    │ ──► runs/<id>/trace.jsonl
              └────────────────────────┘
                          │
                          ▼
              Câu trả lời + trích dẫn ──► runs/<id>/answer.md
```

## Vai trò từng khối

| Khối | File dự kiến | Việc làm | Giống gì ngoài đời |
|---|---|---|---|
| 1. Vòng lặp | `src/agent.py` | Điều khiển: hỏi, chạy, ghi, lặp, dừng | Người quản lý điều phối công việc |
| 2. LLM | `src/llm.py` | Gọi `claude -p` như một hàm: đưa văn bản vào, nhận JSON đúng schema | Chuyên gia ngồi trong phòng kín, chỉ nói, không tự làm |
| 3. Tool | `src/tools/` | Mỗi tool gồm khai báo (JSON schema) + hàm Python chạy thật | Tay chân: tìm kiếm, tải trang, ghi chú, nộp bài |
| 4. Memory | `src/memory.py` | Ngắn hạn: danh sách ghi chú của lần chạy. Dài hạn: SQLite, nhớ nguồn đã đọc và bài học giữa các lần | Sổ tay hôm nay + tủ hồ sơ lâu dài |
| 5. Guard | `src/guard.py` | Kiểm tra mọi lời gọi tool trước khi chạy: được phép? tham số hợp lệ? địa chỉ an toàn? | Bảo vệ ở cửa |
| 6. Trace | `src/trace.py` | Ghi từng bước: LLM nghĩ gì, tool nào, kết quả, token, thời gian | Camera ghi lại mọi việc |

Rule và system prompt là chuỗi nằm trong `src/prompts.py`, không nằm trong file ngoài.

## Một câu hỏi đi qua hệ thống như thế nào

```
1. main.py nhận câu hỏi ──► agent.py bắt đầu, mở trace
2. Vòng lặp: gửi (rule + câu hỏi + ghi chú đã có) cho llm.py
3. LLM trả {"action": "search", "args": {"query": "..."}}
4. guard.py kiểm tra ──► không hợp lệ: trả lỗi cho LLM    hợp lệ: chạy tool
5. Kết quả tool ──► ghi vào memory, ghi vào trace, đưa lại cho LLM
6. Lặp bước 2 đến 5 (search, fetch, save_note...)
7. LLM trả {"action": "finish", "answer": "...", "citations": [...]}
8. guard.py kiểm tra từng trích dẫn có thật nằm trong trang đã đọc
9. Đạt ──► ghi answer.md      Không đạt ──► báo lại LLM sửa (giới hạn số lần)
```

## Cấu trúc thư mục dự kiến

```
research-agent/
├─ README.md          (file này)
├─ src/               code (tạo dần theo từng giai đoạn)
│  ├─ main.py   agent.py   llm.py   prompts.py
│  ├─ memory.py   guard.py   trace.py
│  └─ tools/
├─ corpus/            kho tài liệu thử (trang đã lưu sẵn, chủ đề AI agent)
├─ evals/             bộ bài test và mã chấm điểm
├─ memory/            file SQLite memory dài hạn (không commit)
└─ runs/              kết quả mỗi lần chạy: trace.jsonl, answer.md (không commit)
```

## Lộ trình

| Giai đoạn | Nội dung | Trạng thái |
|---|---|---|
| 1 | Khung agent: vòng lặp, tool đọc `corpus/`, JSON schema, rule trong code | Chưa làm |
| 2 | Trace từng bước, kiểm tra trích dẫn bằng code | Chưa làm |
| 3 | Memory ngắn hạn và dài hạn | Chưa làm |
| 4 | Thêm `fetch_url` và nguồn Wikipedia, arXiv | Chưa làm |
| 5 | Lớp quyền, chống prompt injection, chặn địa chỉ nội bộ | Chưa làm |
| 6 | Bộ eval 4 loại: có đáp án, không có đáp án, mâu thuẫn, chứa lệnh độc | Chưa làm |
| 7 | Chọn model theo việc, đọc song song | Chưa làm |

## Cách gọi LLM (đã thử)

Gọi `claude -p` với các cờ sau để mỗi lần gọi chỉ tốn khoảng 1.000 token (thay vì hơn 58.000):

```
claude -p "<nội dung>" --tools "" --system-prompt "<rule>" --json-schema "<schema>"
       --output-format json --no-session-persistence
       --safe-mode --strict-mcp-config --disable-slash-commands
```

Chạy ở một thư mục trung lập, đưa stdin là rỗng. Không dùng được `--bare` vì nó chỉ nhận API key.
