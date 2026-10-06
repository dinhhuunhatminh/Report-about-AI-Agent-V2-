# Quan sát và đánh giá agent

> Tài liệu thử do Claude soạn cho research-agent, không phải nguồn chính thức.

Agent không chắc chắn như phần mềm thường: cùng một yêu cầu, hai lần chạy có thể đi hai đường khác nhau. Vì vậy cần hai việc. Quan sát trả lời câu hỏi agent vừa làm gì. Đánh giá trả lời câu hỏi agent làm tốt đến đâu và có đang tốt lên hay tệ đi.

Trace là bản ghi đầy đủ một lần chạy, từng bước một. Mỗi lần chạy có một run_id, và mỗi bước ghi lại: thời điểm, tool được gọi cùng tham số, kết quả, số token vào và ra, thời gian của bước và lý do dừng. Nên ghi mỗi sự kiện một dòng JSON (định dạng JSON Lines) để máy lọc và đếm được. Phải che bí mật như token trước khi ghi log.

Eval là bộ bài test cho agent. Mỗi bài gồm đầu vào, môi trường khởi đầu và tiêu chí đạt. Vì agent không cho kết quả giống nhau mỗi lần, mỗi bài nên chạy nhiều lần, ví dụ 5 lần, rồi tính tỉ lệ đạt.

Có ba cách chấm: bằng code (kiểm tra trạng thái cuối, nhanh, rẻ, ổn định, nên ưu tiên), bằng một LLM khác chấm theo tiêu chí (cần kiểm tra lại vì có thể lệch), và bằng người (cho việc khó định nghĩa đúng sai). Nên chấm cả kết quả lẫn đường đi.
