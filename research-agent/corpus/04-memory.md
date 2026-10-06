# Memory của agent

> Tài liệu thử do Claude soạn cho research-agent, không phải nguồn chính thức.

LLM không tự nhớ gì giữa các lần gọi API. Mỗi lần gọi, model chỉ biết đúng những gì được gửi kèm. Cái gọi là "nhớ" là do code lưu lại rồi gửi lại.

Memory ngắn hạn là lịch sử hội thoại của lần chạy hiện tại. Nó bị giới hạn bởi cửa sổ ngữ cảnh (context window) của model. Memory dài hạn là thông tin giữ lại giữa các lần chạy, lưu trong file, cơ sở dữ liệu hoặc kho vector.

Khi lịch sử quá dài sẽ tốn token, có thể chạm trần ngữ cảnh và model dễ bỏ sót chi tiết. Bốn kỹ thuật cắt gọn: giới hạn độ dài kết quả tool, cửa sổ trượt (chỉ giữ N lượt gần nhất), tóm tắt các lượt cũ bằng một lần gọi LLM, và thay kết quả tool cũ bằng dòng "(đã lược bớt)".

Để tìm lại thông tin trong memory dài hạn có hai cách. Tìm theo từ khóa khớp đúng chữ, chính xác với tên riêng, mã lỗi và mã hash. Tìm theo embedding chuyển văn bản thành dãy số biểu diễn ý nghĩa, nên tìm được các câu khác chữ nhưng cùng ý. Với agent nhỏ, nên bắt đầu bằng file và tìm theo từ khóa, chỉ chuyển sang embedding khi dữ liệu nhiều đến mức từ khóa không tìm nổi.
