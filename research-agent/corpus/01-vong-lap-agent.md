# Vòng lặp agent

> Tài liệu thử do Claude soạn cho research-agent, không phải nguồn chính thức.

Agent là chương trình dùng LLM để tự quyết định hành động tiếp theo rồi thực hiện hành động đó qua công cụ (tool), lặp lại cho đến khi xong. LLM chỉ sinh văn bản, nó không tự chạy lệnh. Bên chạy lệnh thật là code của người viết agent.

Mỗi vòng lặp gồm bốn việc: gọi LLM kèm lịch sử và danh sách tool; kiểm tra LLM có yêu cầu dùng tool không; nếu có thì chạy tool và đưa kết quả vào lịch sử; rồi quay lại gọi LLM.

Điều kiện dừng có hai loại: LLM trả lời mà không yêu cầu tool nào, hoặc vòng lặp chạm giới hạn số bước. Với agent nhỏ, giới hạn khuyến nghị là 15 bước mỗi lần chạy. Giới hạn này bắt buộc phải có, vì nếu thiếu thì một lỗi lặp đi lặp lại có thể chạy vô hạn và đốt hết chi phí.

Phần "tự quyết định" của agent thực chất chỉ là vòng lặp này. Mọi tính năng nâng cao như lập kế hoạch, memory hay kiểm tra an toàn đều là code chèn thêm quanh vòng lặp.
