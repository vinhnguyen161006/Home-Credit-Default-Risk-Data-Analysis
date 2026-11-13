# Power BI

Bốn trang báo cáo, nối trực tiếp vào SQL Server. Lưu dạng PBIP để mô hình ngữ nghĩa (TMDL) đọc
được dưới dạng văn bản và diff được trong git — `.pbix` là file nhị phân, không review được.

## Nạp mart trước ML

File `.env` ở thư mục gốc repository đã được cấu hình Windows Authentication và được Git ignore.
Với SQL Authentication, dạng cấu hình thay thế là:

```text
MSSQL_HOST=localhost
MSSQL_PORT=1433
MSSQL_DATABASE=HomeCredit
MSSQL_TRUSTED_CONNECTION=false
MSSQL_SA_PASSWORD=your-existing-sa-password
```

Đặt `MSSQL_TRUSTED_CONNECTION=true` để dùng Windows Authentication; khi đó không cần khai báo
`MSSQL_SA_PASSWORD` và tiến trình phải chạy dưới tài khoản Windows được SQL Server cấp quyền. Thay
host và port bằng địa chỉ TCP thực tế của SQL Server. Tài khoản cần quyền tạo database nếu
`MSSQL_DATABASE` chưa tồn tại, cùng quyền tạo/thay bảng trong database đích. Không dùng
`make mssql-up` nếu đã có SQL Server đang chạy.

Chạy `make serve` để tạo mart từ bảy Silver Parquet rồi nạp 13 bảng vào database. Nếu không có lệnh
`make`, chạy lần lượt `uv run python -m hcr.serving.build_star` và
`uv run python -m hcr.serving.load_sqlserver`.

Trong Power BI Desktop, chọn **Get data → SQL Server**, nhập cùng host/port và database đã cấu hình,
rồi chọn **Import**. Mart gồm:

- Facts: `Fact_Application`, `Fact_BureauLoan`, `Fact_PreviousApplication`.
- Dimensions: `Dim_Customer`, `Dim_Occupation`, `Dim_Organization`, `Dim_Education`,
  `Dim_ContractType`, `Dim_HousingType`, `Dim_FamilyStatus`, `Dim_AgeBand`, `Dim_IncomeBand`,
  `Dim_RiskBand`.

Tạo quan hệ `Dim_Customer.CustomerKey` với `CustomerKey` trên cả ba fact. Nối chín dimension còn lại
vào các khóa tương ứng trên `Fact_Application`; không nối các fact trực tiếp với nhau. `Fact_BureauLoan`
bao gồm cả khoản vay chỉ có ở bureau balance, còn `Fact_PreviousApplication` giữ lại khóa chỉ xuất
hiện trong các bảng lịch sử con.

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
