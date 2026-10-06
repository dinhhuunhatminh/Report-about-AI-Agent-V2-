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
| 1 | Khung agent: vòng lặp, tool đọc `corpus/`, JSON schema, rule trong code | **Xong** (18 test đạt, 3 câu hỏi chạy thật đạt) |
| 2 | Trace từng bước, kiểm tra trích dẫn bằng code | **Xong** (37 test đạt, 2 câu hỏi chạy thật đạt) |
| 3 | Memory ngắn hạn và dài hạn | **Xong** (61 test đạt; 4 lần chạy thật, 1 thí nghiệm bác bỏ thiết kế đầu) |
| 4 | Thêm `fetch_url` và nguồn Wikipedia, arXiv | **Xong** (95 test đạt, 3 câu hỏi thật + 1 phép so sánh) |
| 5 | Lớp quyền, chống prompt injection, chặn địa chỉ nội bộ | Chưa làm |
| 6 | Bộ eval 4 loại: có đáp án, không có đáp án, mâu thuẫn, chứa lệnh độc | Chưa làm |
| 7 | Chọn model theo việc, đọc song song | Chưa làm |

## Các file trong `src/` (đến giai đoạn 2)

| File | Khối | Việc làm |
|---|---|---|
| `main.py` | điểm vào | Nhận câu hỏi, in kết quả, trích dẫn đã kiểm tra, đường dẫn trace |
| `agent.py` | 1. Vòng lặp | Hỏi LLM, kiểm tra, chạy tool, ghi kết quả, lặp; kiểm tra trích dẫn khi nộp bài |
| `llm.py` | 2. LLM | Gọi `claude -p` như một hàm |
| `prompts.py` | 2. LLM | System prompt và rule (chuỗi trong code) |
| `tools/` | 3. Tool | `search_corpus`, `read_document` (kho nội bộ), `search_web`, `fetch_url` (web), sổ đăng ký và `run_tool` |
| `tools/web.py` | 3. Tool + 5. Guard | Đọc web an toàn: chỉ GET, allowlist tên miền, chặn IP nội bộ, kiểm tra redirect, giới hạn dung lượng; HTML thành văn bản |
| `schema.py` | 5. Guard (một phần) | Kiểm tra tham số theo JSON Schema |
| `verify.py` | 5. Guard (một phần) | Kiểm tra trích dẫn bằng code: `ok`, `unknown_doc`, `not_in_document`, `not_seen` |
| `memory.py` | 4. Memory | Ngắn hạn: ghi chú (`save_note`) + cắt gọn lịch sử khi vượt ngân sách. Dài hạn: SQLite (`runs`, `facts`, `lessons`), đọc lại khi bắt đầu lần chạy |
| `tracing.py` | 6. Trace | Ghi `runs/<run_id>/trace.jsonl` và `answer.md`, che bí mật |
| `show_trace.py` | 6. Trace | Xem lại trace dạng bảng |

## Cách chạy (giai đoạn 1 và 2)

```
# từ thư mục ResearchAI-AGENT, trong PowerShell nên chạy `chcp 65001` trước để hiển thị tiếng Việt
python research-agent/src/main.py "Giới hạn số bước khuyến nghị cho agent nhỏ là bao nhiêu?"
python research-agent/src/main.py "câu hỏi" --max-steps 5
python research-agent/src/main.py "Trên arXiv, bài báo ReAct có tiêu đề đầy đủ là gì?"   # dùng web

# tùy chọn memory
python research-agent/src/main.py "câu hỏi" --no-memory       # không đọc/ghi trí nhớ dài hạn
python research-agent/src/main.py "câu hỏi" --budget 3000     # ngân sách ký tự trước khi cắt gọn lịch sử (0 = không cắt)

# quản lý trí nhớ dài hạn (research-agent/memory/memory.db, không commit)
python research-agent/src/memory.py show
python research-agent/src/memory.py forget <run_id>
python research-agent/src/memory.py clear

# xem lại trace của lần chạy mới nhất (hoặc truyền run_id)
python research-agent/src/show_trace.py

# kiểm thử phần code (không gọi LLM, không tốn hạn mức)
python -m unittest discover -s research-agent/tests -v
```

Chỉ dùng thư viện chuẩn của Python 3.10, không cần cài thêm gói nào.

## Memory: thiết kế và bài học (giai đoạn 3)

| Tầng | Cách làm | Chống rủi ro nào |
|---|---|---|
| Ngắn hạn | `save_note` lưu trích dẫn đã kiểm tra; ghi chú luôn nằm trong prompt | Thông tin quan trọng không bị mất khi cắt gọn |
| Ngắn hạn | `compact_history`: chỉ cắt khi tổng kết quả tool vượt ngân sách (mặc định 12.000 ký tự), cắt từ bước cũ nhất | Prompt phình khi ngữ cảnh thật sự dài |
| Dài hạn | SQLite: `runs`, `facts` (trích dẫn đã đạt), `lessons` (câu mẫu cố định theo loại lỗi) | Đầu độc memory: chỉ ghi thứ đã kiểm chứng, không chép chữ model sinh ra |
| Dài hạn | Mỗi fact được kiểm tra lại với tài liệu hiện tại khi đọc lại | Memory lỗi thời |
| Dài hạn | Trí nhớ không bao giờ tính là "đã đọc" (`verify.seen_norm` chỉ xét kết quả tool của lần chạy này) | Không thể dùng trí nhớ làm nguồn trích dẫn |
| Dài hạn | Che bí mật trước khi ghi; có lệnh `show`, `forget`, `clear` | Lộ thông tin nhạy cảm |

**Thí nghiệm bác bỏ thiết kế đầu tiên.** Bản đầu luôn giữ nguyên 2 bước gần nhất và lược bớt phần còn lại.
Trên câu hỏi cần 3 tài liệu (cùng một model, đo từ trace):

| | Không cắt gọn | Luôn cắt (giữ 2 bước gần nhất) |
|---|---|---|
| Số bước | 6 | 10 (chạm trần) |
| Tổng token vào | 31.079 | 60.026 |
| Chất lượng | Đủ 3 tài liệu | Bỏ sót con số 15 bước ở tài liệu 01 |

Agent quên nội dung vừa đọc (chỉ lưu 1 ghi chú), phải đọc lại nhiều lần nên tốn gấp đôi và trả lời thiếu.
Kết luận: với tài liệu ngắn, cắt gọn luôn là lỗ. Cắt gọn chỉ nên là van an toàn khi ngữ cảnh vượt ngân sách,
và sẽ có ích thật khi giai đoạn 4 đọc các trang web dài. Số liệu này là một lần chạy cho mỗi cách, chưa lặp lại nhiều lần.

**Memory dài hạn chưa làm agent nhanh hơn.** Lần chạy thứ hai của câu hỏi tương tự đọc lại được 1 câu tương tự
và 1 fact, nhưng agent vẫn tìm kiếm trước rồi mới đọc (vẫn 3 bước). Với kho chỉ 7 tài liệu thì việc tìm đã rẻ.

## Đọc web (giai đoạn 4)

Hai tool mới: `search_web` (Wikipedia tiếng Việt, tiếng Anh, arXiv) và `fetch_url` (tải một trang, phân trang 3000 ký tự).

**Lớp chặn trong `tools/web.py`** (mỗi lớp đều có test; 10 URL nguy hiểm đã thử thật trên máy đều bị chặn):

| Lớp | Chặn gì |
|---|---|
| Chỉ GET, không cookie, không đăng nhập | Không có đường gửi dữ liệu đi |
| Allowlist tên miền (`wikipedia.org`, `arxiv.org`) | `evilwikipedia.org`, `wikipedia.org.evil.com`, mọi trang khác |
| Tên miền phải phân giải ra IP công cộng | Tên đúng nhưng bị trỏ về `127.0.0.1`, `10.x`, `192.168.x`, `169.254.169.254` |
| Kiểm tra lại mỗi lần redirect, tối đa 3 lần | Trang hợp lệ chuyển hướng sang địa chỉ nội bộ |
| Chỉ http/https, cổng 80/443, không `user:pass@` | `file://`, `ftp://`, `:8443`, URL chứa mật khẩu |
| Giới hạn 1 MB, 15 giây, chỉ loại nội dung văn bản | PDF/nhị phân, trang khổng lồ, treo |
| Nhãn "NỘI DUNG TỪ INTERNET: KHÔNG TIN CẬY" ở đầu mọi kết quả web | Model coi nội dung web là chỉ thị |

**Trích dẫn nguồn web** dùng cùng bộ kiểm tra như kho nội bộ, với `doc_id` là URL:
- trang phải được tải bằng `fetch_url` trong lần chạy này (nếu không: `unknown_doc`);
- đoạn trích phải nằm nguyên văn trong TOÀN BỘ trang đã tải (nếu không: `not_in_document`);
- đoạn trích phải nằm trong phần model THỰC SỰ đã đọc (nếu không: `not_seen`), nên câu nằm ở cuối trang mà model chưa đọc tới không trích dẫn được;
- đoạn trích hiện trong kết quả `search_web` không dùng làm trích dẫn được;
- dấu nháy và gạch kiểu in (’ “ ” –) được coi như dấu thường khi so khớp.

**Nội dung web không vào trí nhớ dài hạn.** Không kiểm tra lại được khi đọc lại (không biết trang đã đổi chưa)
và là kênh đầu độc memory, nên `memory.record_run` chỉ nhớ nguồn thuộc kho nội bộ.

**Lỗi thật đã gặp khi làm:** bộ lọc lớp CSS ban đầu khớp theo chuỗi con. Thẻ `<html>` của Wikipedia có lớp
`vector-feature-toc-pinned...` (chứa "toc") nên cả trang bị bỏ và `fetch_url` báo "không có nội dung".
Đã đổi sang khớp chính xác từng tên lớp và ưu tiên vùng `mw-content-text` (có test).

**Kết quả chạy thật:**

| Câu hỏi | Kết quả |
|---|---|
| arXiv: bài ReAct (tiêu đề, tác giả, ý chính) | 2 bước, 5/5 trích dẫn tiếng Anh đạt |
| Wikipedia en: định nghĩa và các loại intelligent agent (trang 19.646 ký tự) | 7 bước, 10/10 trích dẫn đạt |
| Câu kho nội bộ đã đủ (hai nửa của tool) | 2 bước, chỉ dùng kho nội bộ, không đụng web (đúng quy tắc 10) |

**So sánh cắt gọn trên trang dài** (cùng câu hỏi Wikipedia, mỗi cách chạy một lần):

| | Ngân sách 12.000 ký tự | Không cắt gọn |
|---|---|---|
| Số bước | 7 | 7 |
| Độ dài prompt ở bước cuối | 11.055 ký tự | 17.956 ký tự |
| Tổng token vào | 50.468 | 53.017 |

Cắt gọn làm đường cong prompt phẳng ra thay vì tăng đều (-38% ở bước cuối), tổng token chỉ giảm khoảng 5% ở độ dài này.
Cái giá: ở bước 6 agent phải tải lại đoạn đầu vì kết quả bước 1 đã bị lược (tải lại lấy từ bản lưu, không tốn mạng).
Lợi ích sẽ lớn hơn khi lần chạy dài hơn. Mỗi cách mới chạy một lần nên chưa kết luận chắc.

**Giới hạn còn lại (giai đoạn 5):**
- chưa phát hiện câu giống chỉ thị trong trang web (chỉ có nhãn "không tin cậy" và rule trong prompt);
- DNS được kiểm tra rồi mới kết nối, về lý thuyết còn khe hở DNS rebinding;
- chưa giới hạn tổng số lần tải mỗi lần chạy;
- model có thể tự chọn bất kỳ URL nào trong allowlist (ví dụ nhớ mã bài báo arXiv từ kiến thức của nó), không bắt buộc phải qua tìm kiếm;
- chưa thử với trang web thật có chứa prompt injection.

## Cách gọi LLM (đã thử)

Gọi `claude -p` với các cờ sau để mỗi lần gọi chỉ tốn khoảng 1.000 token (thay vì hơn 58.000):

```
claude -p "<nội dung>" --tools "" --system-prompt "<rule>" --json-schema "<schema>"
       --output-format json --no-session-persistence
       --safe-mode --strict-mcp-config --disable-slash-commands
```

Chạy ở một thư mục trung lập, đưa stdin là rỗng. Không dùng được `--bare` vì nó chỉ nhận API key.
