# Power BI

Bốn trang báo cáo, nối trực tiếp vào SQL Server. Lưu dạng PBIP để mô hình ngữ nghĩa (TMDL) đọc
được dưới dạng văn bản và diff được trong git — `.pbix` là file nhị phân, không review được.

## Bốn trang

| Trang | Câu hỏi trả lời | Nội dung |
| --- | --- | --- |
| Danh mục | cơ cấu đơn vay như thế nào | số đơn, giá trị, tỷ lệ vỡ nợ theo loại hợp đồng, nghề, trình độ |
| Yếu tố rủi ro | nhóm nào rủi ro hơn | tỷ lệ vỡ nợ theo nhóm tuổi, thu nhập, cư trú, hôn nhân |
| Chất lượng mô hình | mô hình hoạt động tốt đến đâu | bảng decile, reliability diagram, AUC trên holdout |
| Ngưỡng quyết định | nên đặt ngưỡng ở đâu | tham số what-if, tỷ lệ duyệt và tổn thất dự kiến |

Trang **Ngưỡng quyết định** là thành phần biến báo cáo thành công cụ ra quyết định thay vì chỉ mô
tả: một tham số what-if điều chỉnh ngưỡng PD, hai measure tính tỷ lệ duyệt và tổn thất tương ứng.

Trang **Chất lượng mô hình** chỉ đọc dữ liệu có `IsHoldout = 1` — phần duy nhất mô hình chưa từng
thấy. Bỏ bộ lọc này là cách báo cáo hiệu năng in-sample như thể out-of-sample.

## Measure cần có

| Measure | Công thức | Định dạng |
| --- | --- | --- |
| Actual Default Rate | `DIVIDE(SUM(TARGET), COUNTROWS(Fact_Application))` | phần trăm |
| Average PD | `AVERAGE(PD_Predicted)` | phần trăm |
| Calibration Gap | `[Average PD] - [Actual Default Rate]` | điểm phần trăm |
| Approval Rate | `DIVIDE(COUNTROWS(FILTER(..., PD < Threshold)), COUNTROWS(...))` | phần trăm |
| Application Count | `COUNTROWS(Fact_Application)` | số nguyên |

**Calibration Gap là measure quan trọng nhất.** Cắt theo giới tính và nhóm tuổi, chính measure này
thực hiện phép kiểm tra công bằng thứ ba: nếu mô hình ước lượng rủi ro của một nhóm cao hơn thực
tế, nhóm đó bị định giá bất lợi một cách có hệ thống dù rủi ro thực tương đương.

## Bốn quy tắc mô hình ngữ nghĩa

1. **Mọi quan hệ một chiều**, từ fact sang dimension. Quan hệ hai chiều làm mẫu số của measure tỷ
   lệ bị lọc theo điều kiện tử số, cho ra kết quả bằng 100% — trông như một con số, thực ra là một
   lỗi.
2. **Quan hệ tạo thủ công**, không dùng auto-detect.
3. **Ngưỡng trong DAX viết dạng phân số.** `DIVIDE` trả giá trị 0–1, nên viết `> 0.07`, không viết
   `> 7`. Định dạng phần trăm đặt ở thuộc tính hiển thị, không đặt trong công thức.
4. **Tắt auto date/time.** Dữ liệu không có cột ngày nào, nên tính năng này chỉ sinh bảng ẩn vô
   ích và làm phình mô hình.

Cột cờ và cột tỷ lệ — `TARGET`, `PD_Predicted`, `CREDIT_INCOME_RATIO` — đặt aggregation mặc định là
**không tổng hợp**. Để mặc định tính tổng sẽ cho ra con số vô nghĩa ngay khi kéo vào biểu đồ.

## TODO

- Dựng `HomeCredit.pbip` nối vào SQL Server, cổng đọc từ cùng một biến `MSSQL_PORT` mà
  `docker-compose.yml` và script nạp dùng. Lệch cổng giữa ba nơi là lỗi thường gặp và khó phát
  hiện vì mỗi bên chỉ báo được là không kết nối được.
- Khai báo 9 quan hệ một chiều từ `Fact_Application` sang các `Dim_*`.
- Viết 5 measure ở bảng trên, kiểm `Calibration Gap` cắt theo `CODE_GENDER` khớp số trong báo cáo
  công bằng — hai nơi lệch nhau nghĩa là một trong hai sai.
- Đặt `SortOrder` làm cột sắp xếp cho `Dim_AgeBand`, `Dim_IncomeBand`, `Dim_RiskBand`,
  `Dim_Education`.
- Dựng tham số what-if cho ngưỡng PD, miền 0,02–0,30 dạng phân số.
- Commit TMDL dạng văn bản, không commit `.pbix`.
