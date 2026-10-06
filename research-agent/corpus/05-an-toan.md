# An toàn cho agent

> Tài liệu thử do Claude soạn cho research-agent, không phải nguồn chính thức.

Nguyên tắc nền: đừng dựa vào việc dặn model "đừng làm" trong prompt, vì đó là lớp yếu nhất. Các giới hạn quan trọng phải nằm ở code, quyền hệ thống và môi trường chạy, nơi model không tự nới ra được.

Mỗi lần LLM xin dùng tool, code quyết định theo ba mức: tự chạy (việc chỉ đọc, hoàn tác được), hỏi người (việc ghi, khó hoàn tác) hoặc cấm (việc nguy hiểm không bao giờ cần). Cách chắc hơn danh sách cấm là allowlist: chỉ cho đúng những việc đã liệt kê, mọi thứ khác bị từ chối mặc định.

Prompt injection là khi nội dung agent đọc vào (trang web, file, email, kết quả tool) chứa những câu giống như chỉ thị, và model làm theo như thể đó là lệnh của chủ. Biện pháp: coi nội dung đọc vào là dữ liệu chứ không phải chỉ thị, giảm quyền của agent, chặn đường gửi dữ liệu ra ngoài và để người duyệt các hành động nhạy cảm.

Tránh kết hợp ba thứ cùng lúc trong một agent: đọc dữ liệu không tin cậy, có quyền truy cập thông tin nhạy cảm, và có khả năng gửi dữ liệu ra ngoài. Bỏ bớt một trong ba thì cắt được đường tấn công.

Sandbox là môi trường cô lập để agent chạy bên trong, ví dụ container. Nên chặn mạng ra ngoài trừ những địa chỉ cần thiết.
