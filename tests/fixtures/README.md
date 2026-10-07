# Test fixtures

Mẫu nhỏ vài chục dòng mỗi bảng. Test không bao giờ chạm dữ liệu thật: 2,5 GB làm bộ test chậm
đến mức không ai chạy nữa, và một quality gate không được chạy thì vô dụng.

Fixture **phải chứa sẵn các bẫy giá trị**, không phải dữ liệu sạch:

| Bẫy | Vì sao cần trong fixture |
| --- | --- |
| `DAYS_EMPLOYED = 365243` | test sentinel pass dễ dàng trên dữ liệu không có sentinel |
| `CODE_GENDER = XNA` | kiểm nhánh null hóa không gán giá trị thay thế |
| `ORGANIZATION_TYPE = XNA` | kiểm nhánh ngược: giữ làm hạng mục riêng |
| `AMT_INCOME_TOTAL` cực đoan | kiểm winsorize giữ nguyên số dòng |
| `EXT_SOURCE_1` null | kiểm null được giữ, không bị điền |
| `OWN_CAR_AGE` null | kiểm không bị điền 0 |
| một `SK_ID_CURR` không có dòng bureau | kiểm LEFT JOIN và `FLAG_NO_BUREAU_HISTORY` |
| một `SK_ID_BUREAU` không có dòng balance | mô phỏng tỷ lệ phủ 48% thực tế |
| `STATUS` đủ mã 1–5, C, null | kiểm từng nhánh predicate delinquency |
| một khoản vay chỉ có 1 tháng | `regr_slope` phải trả null, không trả 0 |
| `AMT_INSTALMENT = 0` | kiểm guard chia cho 0 trả null, không trả vô cực |
| trả muộn, trả sớm, trả đúng hạn, trả thiếu | kiểm dấu và biên của hai đặc trưng trọng yếu |

Tỷ lệ `TARGET` dương trong fixture nên gần 8% và phải có cả hai lớp, nếu không test phân tầng
không kiểm được gì.

## TODO

- Dựng fixture application bằng code trong [conftest.py](../conftest.py), không đọc từ file, để
  các dòng bẫy nhìn thấy được ngay tại chỗ test đọc.
- Nếu một bảng cần file: giữ dưới 100 dòng, lưu `.csv` trong thư mục này (`.gitignore` đã mở
  ngoại lệ cho `tests/fixtures/**`).
- Không sinh fixture bằng cách lấy mẫu ngẫu nhiên từ dữ liệu thật. Mẫu ngẫu nhiên gần như chắc
  chắn không chứa bẫy nào, và fixture sẽ im lặng ngừng kiểm những thứ nó được tạo ra để kiểm.
