# Tool (công cụ) của agent

> Tài liệu thử do Claude soạn cho research-agent, không phải nguồn chính thức.

Một tool gồm hai nửa tách biệt. Nửa thứ nhất là bản khai báo, gửi kèm mỗi lần gọi LLM, để LLM biết có tool gì và dùng thế nào. Nửa thứ hai là hàm thực thi trong code, chạy thật khi LLM yêu cầu. LLM chỉ nhìn thấy bản khai báo, không thấy code bên trong.

Bản khai báo có ba trường bắt buộc: name (tên tool), description (tool làm gì và khi nào dùng) và input_schema (mô tả tham số theo chuẩn JSON Schema). Trong ba trường này, description quan trọng nhất vì LLM dựa vào nó để quyết định dùng tool nào.

Không được tin tham số mà LLM gửi. Code phải kiểm tra trước khi chạy: có đủ tham số bắt buộc không, đúng kiểu không, giá trị có nằm trong danh sách cho phép (allowlist) không, đường dẫn có nằm trong thư mục cho phép không.

Kết quả của tool nên là văn bản và có giới hạn độ dài, ví dụ cắt ở 20000 ký tự, để không làm phình ngữ cảnh. Khi tool lỗi, không để chương trình sập. Hãy trả thông báo lỗi cụ thể về cho LLM, kèm cờ is_error, để LLM tự sửa hoặc thử cách khác.
