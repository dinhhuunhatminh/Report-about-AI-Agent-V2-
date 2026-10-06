# MCP (Model Context Protocol)

> Tài liệu thử do Claude soạn cho research-agent, không phải nguồn chính thức.

MCP là chuẩn mở để agent dùng tool do bên khác cung cấp, thay vì tự viết từng tool. Có thể hình dung nó như cổng USB chung giữa agent và các dịch vụ như GitHub, cơ sở dữ liệu hay hệ thống file.

MCP có hai vai trò. MCP server chạy riêng, công bố danh sách tool của nó (tên, mô tả, schema) và tự thực thi khi được gọi. MCP client nằm trong agent: nó hỏi server có những tool gì, đưa danh sách đó vào bản khai báo gửi cho LLM, và khi LLM yêu cầu dùng tool thì chuyển lời gọi sang server. Hai thao tác cơ bản của giao thức là tools/list (liệt kê tool) và tools/call (gọi tool).

Có hai cách kết nối. Server cục bộ chạy như một tiến trình con trên máy, nói chuyện qua đầu vào và đầu ra chuẩn (stdio). Server ở xa nói chuyện qua HTTP.

Về an toàn: server bên thứ ba có thể chạy code trên máy hoặc giữ token của bạn. Chỉ dùng server đáng tin, cấp token với quyền tối thiểu, và chỉ bật những tool thật sự cần.
