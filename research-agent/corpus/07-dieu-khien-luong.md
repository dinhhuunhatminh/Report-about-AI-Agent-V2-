# Điều khiển luồng của agent

> Tài liệu thử do Claude soạn cho research-agent, không phải nguồn chính thức.

Điều khiển luồng là câu hỏi: ai quyết định bước tiếp theo? Với workflow, code quyết định theo thứ tự viết sẵn và LLM chỉ xử lý từng bước nhỏ. Với agent, LLM tự quyết định gọi tool nào và khi nào dừng. Workflow dễ dự đoán và dễ kiểm thử hơn, agent linh hoạt hơn. Nên dùng luồng cố định cho những gì đã biết chắc, và chỉ để LLM tự quyết ở chỗ thật sự cần linh hoạt.

Có hai cách lập kế hoạch. Cách thứ nhất là vừa làm vừa nghĩ, gọi là ReAct: mỗi vòng nghĩ một bước, gọi tool, đọc kết quả rồi nghĩ tiếp. Cách thứ hai là lập kế hoạch trước rồi mới thực hiện, cho phép người duyệt kế hoạch trước khi chạy thật.

Khi lỗi xảy ra, phân biệt hai loại. Lỗi hạ tầng như mạng đứt hay API quá tải thì code tự thử lại, chờ lâu dần giữa các lần (1 giây, 2 giây, 4 giây), tối đa 3 lần. Lỗi của tool như file không tồn tại thì trả lỗi về cho LLM để nó tự quyết sửa gì, không thử lại mù quáng.

Khi cách làm hiện tại không hiệu quả, agent đổi hướng theo ba mức: lập lại kế hoạch, dùng phương án dự phòng, hoặc chuyển cho người xử lý. Cần chốt trước các tín hiệu nhận ra đang đi sai, ví dụ lặp lại cùng một lệnh nhiều lần hoặc chạm trần số bước.
