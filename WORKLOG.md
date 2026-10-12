# WORKLOG — Home Credit Default Risk

Danh sách các task cần làm để hoàn thành dự án.

Tài liệu liên quan: [CLAUDE.md](CLAUDE.md) (luật viết code) · [docs/](docs/) (đặc tả nghiệp vụ) · [README.md](README.md)

## 0. Hiện trạng

Repo đã có đủ khung thư mục, file cấu hình YAML, file SQL và test. Tuy vậy, **cả 29 module Python trong `src/hcr/` và `reports/` mới là khung**: mỗi hàm đã có tên và docstring nhưng thân hàm chỉ `raise NotImplementedError`. Test tương ứng đang bị skip tự động (xem `tests/conftest.py`).

Nói cách khác, khung đã dựng xong, việc còn lại là viết phần ruột. Mỗi task bên dưới chỉ rõ cần viết ruột cho file nào.

## 1. Nguyên tắc

- **Làm task theo thứ tự.** Task sau dùng kết quả của task trước. Một task chỉ coi là xong khi đạt mục "Xong khi" của nó, kiểm chứng bằng lệnh chạy được, không phải bằng cảm giác.
- **Ba thứ không được đảo thứ tự:**
  1. Tách holdout (Task 5) phải xong trước khi tạo đặc trưng (Task 6).
  2. Mô hình mốc và kiểm tra rò rỉ (Task 7, 8) phải xong trước mô hình chính (Task 9).
  3. Holdout chỉ được mở một lần (Task 11), và chỉ sau khi mô hình đã đóng băng (cuối Task 10).
- **Mỗi task (hoặc một phần task) làm trên một nhánh riêng**, không commit thẳng vào `main`.
- **Một thay đổi xong khi** đạt checklist §13 của [CLAUDE.md](CLAUDE.md): `ruff`, `mypy`, `pytest` sạch; có test cho hành vi mới; không comment `#`; không tiếng Việt trong code; không magic number.
- **Viết hàm nào thì gỡ skip và viết test của hàm đó cùng lúc.** Khi xong Task 13, không còn test nào bị skip.
- **Xong bước nào thì nối bước đó vào pipeline chung**: thêm vào `src/hcr/pipeline/run_all.py` và target tương ứng trong `Makefile`. Như vậy lệnh `make all` lớn dần theo từng task, không dồn việc nối vào cuối.

### Giải thích vài thuật ngữ dùng trong file này

| Thuật ngữ | Nghĩa |
| --- | --- |
| bronze / silver | Hai tầng dữ liệu. *Bronze* là bản sao nguyên vẹn của CSV ở dạng Parquet. *Silver* là bản đã sửa các giá trị sai, vẫn giữ nguyên số dòng. |
| holdout | 20% hồ sơ được cất riêng từ đầu. Mô hình không bao giờ được học trên phần này; nó chỉ dùng để chấm điểm một lần ở cuối dự án. |
| rò rỉ (leakage) | Thông tin mà lúc xét duyệt thật không thể có, nhưng lại lọt vào dữ liệu huấn luyện. Hậu quả là mô hình trông rất giỏi khi thử, nhưng ra thực tế thì kém. |
| gate (cổng kiểm tra) | Một hàm kiểm tra trả về đạt/không đạt. Không đạt thì pipeline dừng lại. |
| fold, CV | Cross-validation: chia tập train thành 5 phần, lần lượt học trên 4 phần và chấm trên phần còn lại. |
| AUC | Thước đo khả năng xếp hạng người rủi ro cao lên trên người rủi ro thấp. 0,5 là đoán bừa, 1,0 là hoàn hảo. |
| hiệu chỉnh (calibration) | Chỉnh lại xác suất mô hình đưa ra cho khớp với thực tế. Ví dụ, trong nhóm được dự báo 10% thì phải có khoảng 10% người vỡ nợ thật. |

## 2. Tổng quan 13 task

| # | Task | Cần xong trước | Lệnh chạy | Trạng thái |
| --- | --- | --- | --- | --- |
| 1 | Chuẩn bị môi trường | — | `make install`, `make check` | chưa |
| 2 | Chuyển CSV sang Parquet | 1 | `make ingest` | chưa |
| 3 | Kiểm tra dữ liệu đầu vào | 2 | `make contracts` | chưa |
| 4 | Làm sạch dữ liệu | 3 | `make silver` | chưa |
| 5 | Tách holdout | 4 | `make split` | chưa |
| 6 | Tạo đặc trưng | **5** | `make features` | chưa |
| 7 | Lọc đặc trưng và chặn rò rỉ | 6 | `make gates` | chưa |
| 8 | Mô hình mốc | 4 (và file tỷ lệ của Task 6) | `make train` | chưa |
| 9 | Mô hình chính | **7**, 8 | `make train` | chưa |
| 10 | Hiệu chỉnh, chọn ngưỡng, quy điểm | 9 | `make train` | chưa |
| 11 | Đánh giá cuối trên holdout | **10 (đã đóng băng)** | `make evaluate` | chưa |
| 12 | Kho dữ liệu cho báo cáo | 10 (tạm dùng dự đoán OOF của Task 9) | `make mssql-up`, `make serve` | chưa |
| 13 | Dashboard, tài liệu, nối pipeline | 11, 12 | `make readme`, `make all` | chưa |

Hai cặp task làm song song được: Task 8 song song với Task 6–7, và Task 12 song song với Task 9–10.

## 3. Chi tiết từng task

---

### Task 1 — Chuẩn bị môi trường

**Lệnh:** `make install`, `make check`

**Mục đích.** Ai clone repo về cũng cài được đúng phiên bản thư viện và chạy ra kết quả giống hệt nhau. Đây cũng là nơi đặt sẵn các công cụ tự động bắt lỗi: format code, kiểm tra kiểu, và chặn comment `#`.

**Cần làm**
1. Ghi đủ thư viện vào `pyproject.toml` với phiên bản cố định, rồi tạo lockfile bằng `uv lock`.
2. Kiểm tra cấu hình ruff trong `pyproject.toml`: độ dài dòng 100, bật rule `ERA` (chặn code bị comment) và `T20` (chặn `print`). Bật mypy ở chế độ strict.
3. Viết `paths.py`: mọi đường dẫn thư mục (`data/raw`, `data/bronze`, `data/silver`, `data/splits`, `data/features`, `data/models`) khai báo tại một chỗ, dùng `pathlib.Path`.
4. Viết `config.py`: đọc 5 file YAML trong `configs/` thành đối tượng có kiểu rõ ràng. Thiếu khóa thì báo lỗi ngay, không lặng lẽ dùng giá trị mặc định.
5. Đối chiếu `.gitignore`: phải chặn `data/`, `archive/`, `*.csv`, `*.parquet`, `mlruns/`, `*.pkl`, `*.joblib`, `.env`.
6. Dựng dữ liệu mẫu trong `tests/conftest.py`: vài chục dòng giả lập cho mỗi bảng, **cố ý chứa đủ 7 lỗi dữ liệu** ở Task 4 để các test sau có cái mà kiểm tra.

**File cần code**

| File | Viết gì |
| --- | --- |
| `pyproject.toml` | danh sách thư viện có pin phiên bản; cấu hình ruff, mypy, pytest |
| `uv.lock` | **tạo mới** bằng `uv lock` |
| `src/hcr/paths.py` | hằng số đường dẫn cho từng tầng dữ liệu |
| `src/hcr/config.py` | hàm đọc và kiểm tra 5 file YAML |
| `.gitignore`, `.env.example` | rà lại cho đủ mục |
| `tests/conftest.py` | fixture dữ liệu mẫu có sẵn các lỗi dữ liệu |
| `.github/workflows/ci.yml` | CI chạy `ruff`, `mypy`, `pytest` mỗi khi có PR |

**Xong khi**
- Trên một máy mới, `uv sync` rồi `make check` chạy không lỗi.
- `config.py` đọc được cả 5 file YAML. Xóa thử một khóa thì nó báo lỗi rõ ràng.

---

### Task 2 — Chuyển CSV sang Parquet (bước 1 của pipeline)

**Lệnh:** `make ingest`

**Mục đích.** 8 file CSV có tổng cộng khoảng 58 triệu dòng, đọc rất chậm và tốn ổ đĩa. Chuyển sang Parquet (định dạng cột, có nén) giúp mọi bước sau đọc nhanh hơn nhiều lần. Bước này **chỉ đổi định dạng, không đụng vào nội dung**.

**Cần làm**
1. Dùng DuckDB đọc từng file CSV trong `data/raw/`, ghi ra Parquet nén trong `data/bronze/`, mỗi bảng một file.
2. Giữ nguyên tên cột, kiểu dữ liệu và số dòng.
3. Ghi log số dòng của từng bảng sau khi chuyển.

**File cần code**

| File | Viết gì |
| --- | --- |
| `src/hcr/ingest/to_parquet.py` | hàm chuyển một CSV sang Parquet và hàm chạy cho cả 8 bảng |
| `tests/unit/test_ingest.py` | **tạo mới**: chuyển một CSV mẫu nhỏ, kiểm tra số dòng và tên cột giữ nguyên |

**Xong khi**
- `data/bronze/` có đủ 8 file Parquet, số dòng khớp bảng ở §2 của CLAUDE.md.
- Chạy hai lần ra file giống hệt nhau, và file CSV gốc không bị thay đổi.

---

### Task 3 — Kiểm tra dữ liệu đầu vào (bước 2)

**Lệnh:** `make contracts`

**Mục đích.** Trước khi tốn công xử lý, phải chắc dữ liệu đầu vào đúng như mô tả: đủ dòng, đủ cột, đúng kiểu, khóa không trùng. Nếu file tải về bị thiếu hoặc hỏng, pipeline dừng ngay tại đây thay vì cho ra kết quả sai ở cuối.

**Cần làm**
1. Viết schema Pandera cho 8 bảng, dựa trên số liệu khai báo trong `configs/data_contract.yml`.
2. Kiểm tra số dòng, số cột và kiểu dữ liệu của từng bảng.
3. Kiểm tra khóa không trùng: `SK_ID_CURR` trong `application_train`, `SK_ID_BUREAU` trong `bureau`.
4. Hàm kiểm tra phải chạy riêng được, **không nhúng vào hàm đọc dữ liệu**.

**File cần code**

| File | Viết gì |
| --- | --- |
| `src/hcr/contracts/schemas.py` | schema Pandera cho từng bảng |
| `src/hcr/contracts/validate_raw.py` | hàm chạy kiểm tra trên `data/bronze/`, trả về đạt/không đạt kèm lý do |
| `configs/data_contract.yml` | rà lại số dòng và số cột cho khớp dữ liệu thật |
| `tests/gates/test_contract_raw.py` | test cả trường hợp đạt lẫn không đạt: thiếu dòng, sai cột, trùng khóa |

**Xong khi**
- Kiểm tra đạt trên dữ liệu thật.
- Cố ý làm hỏng dữ liệu mẫu (thêm một dòng trùng khóa chẳng hạn) thì kiểm tra báo không đạt.

---

### Task 4 — Làm sạch dữ liệu (bước 3, tầng silver)

**Lệnh:** `make silver`

**Mục đích.** Dữ liệu gốc có nhiều giá trị "giả": mã đặc biệt, giá trị thiếu ghi bằng chữ, số ngoại lai. Nếu không xử lý, mọi phép trung bình và tổng hợp phía sau đều sai. Ví dụ, `DAYS_EMPLOYED = 365243` tương đương 1.000 năm đi làm; để nguyên thì nó kéo lệch mọi phép tính có cột này.

Nguyên tắc xuyên suốt: **thiếu dữ liệu không có nghĩa là bằng 0.** Giá trị thiếu giữ là null và thêm một cột cờ để đánh dấu, không điền 0.

**Cần làm.** Xử lý 7 lỗi bắt buộc trong bảng application:

| Cột | Lỗi | Cách xử lý |
| --- | --- | --- |
| `DAYS_EMPLOYED` | `365243` là mã cho người không đi làm (~18%) | đổi thành null, thêm cờ `FLAG_NO_EMPLOYMENT` |
| `DAYS_BIRTH` | luôn là số âm | thêm cột `AGE_YEARS = -DAYS_BIRTH / 365.25` |
| `CODE_GENDER` | 4 dòng có giá trị `XNA` | đổi thành null, không gán giá trị thay thế |
| `ORGANIZATION_TYPE` | ~18% có giá trị `XNA`, chủ yếu là người nghỉ hưu | giữ như một nhóm riêng, không coi là thiếu |
| `AMT_INCOME_TOTAL` | có thu nhập 117 triệu | winsorize ở phân vị 99,9 hoặc lấy log; **không xóa dòng** |
| `EXT_SOURCE_1` | thiếu ~56% | giữ null, thêm cờ thiếu |
| `OWN_CAR_AGE` | thiếu ~66% vì không có xe | giữ null, **không điền 0** |

Với 6 bảng lịch sử, đổi các giá trị `XNA` và `XAP` thành null, và thêm cờ cho biết khách có lịch sử ở từng nguồn hay không. Mỗi bảng nguồn cho ra một bảng silver **cùng số dòng**.

Dùng hai notebook EDA để xác nhận 7 lỗi trên có thật trong dữ liệu, với đúng tỷ lệ như mô tả.

**File cần code**

| File | Viết gì |
| --- | --- |
| `src/hcr/silver/clean_application.py` | xử lý 7 lỗi của bảng application |
| `src/hcr/silver/clean_history.py` | xử lý `XNA`/`XAP` của 6 bảng lịch sử |
| `src/hcr/silver/flags.py` | sinh cột cờ: cờ thiếu, cờ không đi làm, cờ có lịch sử |
| `configs/silver_rules.yml` | rà lại danh sách cột và quy tắc cho khớp dữ liệu thật |
| `tests/unit/test_silver_rules.py` | **mỗi lỗi trong 7 lỗi một test riêng**, kèm test gate bước 3 |
| `notebooks/01_eda_application.ipynb`, `notebooks/02_eda_history_tables.ipynb` | EDA xác nhận lỗi (chỉ để khám phá, không chứa logic pipeline) |

**Xong khi**
- Không cột `DAYS_*` nào còn giá trị `365243`.
- Mọi cột `DAYS_*` đều ≤ 0.
- Số dòng silver bằng số dòng bronze ở từng bảng.

---

### Task 5 — Tách holdout (bước 4)

**Lệnh:** `make split`

**Mục đích.** Cất riêng 20% hồ sơ để cuối dự án chấm điểm mô hình trên dữ liệu nó chưa từng thấy. Đây là con số duy nhất phản ánh hiệu năng thật.

> ⚠️ **Task này bắt buộc xong trước Task 6.** Tạo đặc trưng trước rồi mới tách là nguồn rò rỉ số một: mô hình trông tốt hơn thực tế 0,02–0,05 AUC.

**Cần làm**
1. Rút ngẫu nhiên 20% `SK_ID_CURR` từ silver application, với seed lấy từ `configs/model.yml`.
2. Rút theo tầng: tỷ lệ vỡ nợ ở phần holdout và phần train phải gần như bằng nhau.
3. Ghi danh sách id ra `data/splits/holdout_ids.parquet`, để mọi lần chạy sau dùng đúng danh sách đó.
4. Làm cơ chế "chỉ đọc một lần": mỗi lần có code đọc nhãn của holdout thì ghi một dòng vào `holdout_usage.json`. Muốn đọc lần thứ hai thì phải dùng cờ `--force` kèm lý do, và lý do đó được ghi luôn vào `holdout_usage.json`.

**File cần code**

| File | Viết gì |
| --- | --- |
| `src/hcr/split/make_holdout.py` | hàm tách, hàm ghi file id, cơ chế ghi nhận số lần đọc |
| `configs/model.yml` | đã có `holdout_fraction: 0.20` và `random_seed: 42`, chỉ cần rà lại |
| `tests/gates/test_split_disjoint.py` | test hai tập không trùng nhau, tỷ lệ vỡ nợ lệch < 0,1 điểm %, chạy lại ra cùng kết quả |

**Xong khi**
- `holdout_ids.parquet` có đúng 61.502 id.
- Không id nào nằm ở cả hai tập.
- Tỷ lệ vỡ nợ hai tập lệch dưới 0,1 điểm phần trăm.

---

### Task 6 — Tạo đặc trưng (bước 5)

**Lệnh:** `make features` · **Cần có:** Task 5 xong

**Mục đích.** Mô hình cần mỗi khách đúng một dòng, nhưng lịch sử của họ nằm rải rác trong 58 triệu dòng ở 6 bảng. Task này gộp toàn bộ lịch sử thành **307.511 dòng, mỗi khách một dòng**, với vài trăm cột mô tả hành vi vay và trả nợ.

**Cần làm**
1. **Viết `application_ratios.sql` trước tiên**, vì Task 8 cần nó cho mô hình mốc số 2. File này tính 6 tỷ lệ bắt buộc:
   - khoản vay / thu nhập
   - tiền trả hàng kỳ / thu nhập
   - khoản vay / giá hàng hóa
   - khoản vay / tiền trả hàng kỳ
   - số ngày đi làm / tuổi
   - thu nhập / số người trong gia đình
2. Gộp hai tầng bằng SQL trên DuckDB:
   - `bureau_balance` → gộp theo từng khoản vay ngoài → nối vào `bureau` → gộp theo từng khách.
   - `POS_CASH_balance`, `installments_payments`, `credit_card_balance` → gộp theo từng đơn vay cũ → nối vào `previous_application` → gộp theo từng khách.
   - **Luôn dùng `LEFT JOIN`** để không mất khách chưa có lịch sử. Khách không có lịch sử thì cột để null, không điền 0.
3. Tạo 4 nhóm đặc trưng:
   - **Tỷ lệ** trên đơn hiện tại (bước 1 ở trên).
   - **Thống kê toàn lịch sử**: đếm, tổng, trung bình, lớn nhất, nhỏ nhất, độ lệch chuẩn.
   - **Thống kê theo cửa sổ** 3, 6, 12, 24 tháng gần nhất. Đây là nhóm giá trị nhất: hành vi 3 tháng gần đây nói nhiều hơn hành vi 4 năm trước.
   - **Xu hướng**: số dư đang tăng hay giảm theo thời gian (`regr_slope`).
4. Từ `installments_payments`, tạo thêm hai đặc trưng quan trọng:
   - số ngày trả muộn, lấy trung bình, lớn nhất và tỷ lệ số lần trả muộn;
   - tỷ lệ trả đủ, trong đó dưới 1 nghĩa là trả thiếu.
5. Khai báo "cột nào × phép tính nào" trong `configs/features.yml`. `build.py` đọc file này rồi sinh SQL, **không viết vòng lặp quét toàn bộ cột**.
6. Rút gọn 47 cột mô tả căn hộ trước khi gộp: ba biến thể `_AVG`, `_MODE`, `_MEDI` gần như trùng nhau, chỉ giữ một.
7. Ghi manifest đi kèm ma trận: danh sách cột, mỗi cột tính bằng phép gì từ bảng nào, và mã hash của dữ liệu nguồn.
8. Tên cột theo quy ước `<NGUỒN>_<CỘT>_<PHÉP TÍNH>`, ví dụ `BURO_AMT_CREDIT_SUM_MEAN`, `INST_DPD_MEAN_3M`. Chỉ dùng các tiền tố `APP_`, `BURO_`, `BB_`, `PREV_`, `POS_`, `INST_`, `CC_`.

**File cần code**

| File | Viết gì |
| --- | --- |
| `src/hcr/features/sql/application_ratios.sql` | 6 tỷ lệ bắt buộc và các tỷ lệ phụ |
| `src/hcr/features/sql/bureau_balance_agg.sql` | `bureau_balance` → grain khoản vay ngoài |
| `src/hcr/features/sql/bureau_agg.sql` | `bureau` (đã nối kết quả trên) → grain khách |
| `src/hcr/features/sql/pos_cash_agg.sql` | `POS_CASH_balance` → grain đơn vay cũ |
| `src/hcr/features/sql/installments_agg.sql` | `installments_payments` → grain đơn vay cũ, gồm ngày trả muộn và tỷ lệ trả đủ |
| `src/hcr/features/sql/credit_card_agg.sql` | `credit_card_balance` → grain đơn vay cũ |
| `src/hcr/features/sql/previous_agg.sql` | `previous_application` (đã nối 3 bảng trên) → grain khách |
| `src/hcr/features/build.py` | đọc `features.yml`, sinh và chạy SQL, nối tất cả thành ma trận, ghi manifest |
| `configs/features.yml` | danh sách cột × phép tính cho từng nguồn |
| `tests/unit/test_features_sql.py` | test trên dữ liệu mẫu: số dòng đúng, khách không có lịch sử ra null chứ không ra 0, tỷ lệ tính đúng |

**Xong khi**
- Ma trận `data/features/` có đúng 307.511 dòng, mỗi `SK_ID_CURR` một dòng.
- Mọi cột tra được nguồn gốc trong manifest.
- Chạy hai lần cho manifest giống hệt nhau.

---

### Task 7 — Lọc đặc trưng và chặn rò rỉ (bước 6)

**Lệnh:** `make gates`

**Mục đích.** Task 6 sinh ra vài trăm cột, trong đó có cột vô dụng (gần như toàn null, chỉ một giá trị, trùng cột khác) và có thể có cột "biết trước đáp án". Task này dọn các cột vô dụng, và quan trọng hơn là **chặn rò rỉ trước khi huấn luyện**.

Lớp phòng thủ quan trọng nhất là kiểm tra AUC từng cột. Một cột đứng riêng mà đạt AUC trên 0,95 trong bài toán tín dụng thì gần như chắc chắn là rò rỉ, không phải phát hiện hay. Để so sánh: cả ba cột `EXT_SOURCE_*` cộng lại cũng chỉ đạt khoảng 0,70.

**Cần làm**
1. Loại cột theo tiêu chí **cố định từ trước**, không chỉnh theo kết quả AUC:
   - trên 95% null;
   - chỉ có một giá trị;
   - hai cột tương quan |r| > 0,98 thì bỏ một.
2. Dừng pipeline nếu có cột chứa giá trị vô cực, thường do chia cho 0.
3. Tính AUC của từng cột đứng riêng, **chỉ trên tập train**. Cột nào trên 0,95 thì dừng lại và điều tra.
4. Xuất hai phiên bản ma trận:
   - `full`: có `EXT_SOURCE_1/2/3`, cho hiệu năng tốt nhất.
   - `no_ext_source`: bỏ ba cột đó, để đo sức mạnh của dữ liệu nội bộ. Chỉ bản này dùng cho phân tích nghiệp vụ.
5. Ghi log mọi cột bị loại kèm lý do.

**File cần code**

| File | Viết gì |
| --- | --- |
| `src/hcr/quality/feature_gates.py` | gate null, hằng số, vô cực, tương quan |
| `src/hcr/quality/leakage_checks.py` | gate AUC từng cột, ngưỡng 0,95 |
| `src/hcr/features/select.py` | áp kết quả lọc, sinh hai phiên bản `full` và `no_ext_source` |
| `configs/features.yml` (mục `selection`, `configurations`) | ngưỡng lọc và danh sách cột của từng phiên bản |
| `tests/gates/test_feature_gates.py` | mỗi gate một cặp test: đạt và không đạt. Ví dụ, thêm một cột sao chép `TARGET` thì gate AUC phải bắt được. |

**Xong khi**
- Không cột nào có AUC đơn lẻ vượt 0,95.
- Không cột nào chứa giá trị vô cực.
- Có đủ hai phiên bản ma trận, và log ghi lại các cột đã bị loại.

---

### Task 8 — Mô hình mốc

**Lệnh:** `make train` · **Làm song song được với:** Task 6–7

**Mục đích.** Muốn biết mô hình chính "tốt" đến đâu thì cần mốc để so. Mô hình mốc trả lời hai câu hỏi: đoán bừa được bao nhiêu, và chỉ dùng điểm của bên thứ ba thì được bao nhiêu. Task này cũng dựng sẵn công cụ đo dùng chung cho mọi task mô hình về sau.

**Cần làm**
1. Viết các hàm đo: AUC, PR-AUC, Brier score, và khoảng tin cậy 95% của AUC (công thức Hanley–McNeil). **Không dùng accuracy**: đoán tất cả "không vỡ nợ" đã đạt 91,93% accuracy.
2. Dựng sklearn `Pipeline` cho logistic regression và LightGBM. Mọi bước phụ thuộc dữ liệu (điền thiếu, chuẩn hóa, mã hóa) phải nằm **bên trong** Pipeline, để chỉ học trên phần train của từng fold.
3. Chạy 3 mô hình mốc bằng CV 5 fold trên tập train, ghi kết quả vào MLflow:

   | # | Mô hình | AUC kỳ vọng |
   | --- | --- | --- |
   | 0 | Đoán cùng một xác suất (8,07%) cho mọi người | 0,500 |
   | 1 | Logistic chỉ dùng `EXT_SOURCE_1/2/3` | ~0,70 |
   | 2 | Logistic dùng các cột application và 6 tỷ lệ | ~0,74 |

**File cần code**

| File | Viết gì |
| --- | --- |
| `src/hcr/evaluation/metrics.py` | AUC, PR-AUC, Brier |
| `src/hcr/evaluation/confidence.py` | khoảng tin cậy AUC theo Hanley–McNeil |
| `src/hcr/modeling/pipeline.py` | hàm dựng Pipeline cho logistic và LightGBM |
| `src/hcr/modeling/baselines.py` | chạy 3 mô hình mốc, ghi MLflow |
| `configs/model.yml` (mục `baselines`, `cross_validation`, `mlflow`) | rà lại |
| `tests/unit/test_metrics.py` | **tạo mới**: kiểm tra chỉ số và khoảng tin cậy trên ví dụ tính tay được |

**Xong khi:** MLflow có 3 lần chạy với AUC gần các giá trị trong bảng, mỗi số kèm khoảng tin cậy.

---

### Task 9 — Mô hình chính

**Lệnh:** `make train` · **Cần có:** gate AUC của Task 7 đã đạt

> ⚠️ **Chỉ chạy trên dữ liệu thật sau khi gate AUC của Task 7 đạt.** Trước đó, chỉ viết và thử code trên dữ liệu mẫu.

**Mục đích.** Huấn luyện mô hình cho dự đoán tốt nhất, và kiểm tra rằng kết quả tốt đó không đến từ rò rỉ.

**Cần làm**
1. Huấn luyện LightGBM bằng CV 5 fold phân tầng theo `TARGET`, cho cả hai phiên bản `full` và `no_ext_source`. Ghi mọi lần chạy vào MLflow.
2. Xử lý mất cân bằng (11 người tốt : 1 người vỡ nợ) bằng `scale_pos_weight`. **Không dùng SMOTE** hay bất kỳ cách sinh mẫu nhân tạo nào.
3. Lưu dự đoán out-of-fold (OOF): mỗi hồ sơ train được chấm bởi mô hình chưa học hồ sơ đó. Task 10 và Task 12 dùng các dự đoán này.
4. Kiểm định bỏ đặc trưng: lấy 5 đặc trưng mạnh nhất, mỗi lần bỏ một cái rồi huấn luyện lại, ghi bảng AUC. Nếu bỏ một cột mà AUC sụt mạnh thì cột đó đang gánh quá nhiều, cần điều tra.
5. Không dùng chia theo thời gian (time-based split): dữ liệu không có ngày tháng, và `SK_ID_CURR` không đảm bảo tăng theo thời gian.

**File cần code**

| File | Viết gì |
| --- | --- |
| `src/hcr/modeling/train.py` | vòng CV 5 fold, huấn luyện hai phiên bản, lưu dự đoán OOF, ghi MLflow |
| `src/hcr/quality/leakage_checks.py` | thêm hàm kiểm định bỏ đặc trưng |
| `configs/model.yml` (mục `lightgbm`, `class_imbalance`) | siêu tham số, `scale_pos_weight` |
| `tests/unit/test_train.py` | **tạo mới**: trên dữ liệu mẫu, các fold giữ tỷ lệ vỡ nợ, không id nào nằm trong cả train và validation của cùng fold, không đụng tới holdout |

**Xong khi**
- AUC CV của `full` khoảng 0,78–0,79, của `no_ext_source` khoảng 0,74.
- AUC giữa 5 fold lệch nhau dưới 0,02.
- Đã có bảng kết quả bỏ đặc trưng.

> 🛑 **AUC trên 0,85 là dấu hiệu rò rỉ, không phải kết quả tốt.** Dừng lại và điều tra trước khi làm tiếp.

---

### Task 10 — Hiệu chỉnh xác suất, chọn ngưỡng, quy ra điểm tín dụng

**Lệnh:** `make train`

**Mục đích.** Mô hình chính xếp hạng tốt, nhưng con số xác suất nó đưa ra thường lệch cao vì đã dùng `scale_pos_weight`. Muốn ra quyết định cho vay thì xác suất phải đúng thang đo. Task này làm ba việc: chỉnh xác suất cho khớp thực tế, chọn ngưỡng duyệt hay từ chối dựa trên tiền, và đổi xác suất thành điểm tín dụng dễ hiểu.

**Cần làm**
1. **Hiệu chỉnh** bằng isotonic regression, học trên một fold riêng mà mô hình chưa học. Kiểm tra bằng Brier score và reliability diagram (biểu đồ so xác suất dự báo với tỷ lệ vỡ nợ thật).
   - AUC không đổi sau hiệu chỉnh, vì thứ tự xếp hạng không đổi. **Đừng dùng AUC để đánh giá hiệu chỉnh.**
2. **Chọn ngưỡng theo chi phí**, không dùng 0,5:
   - Từ chối nhầm một người tốt: mất `AMT_CREDIT × biên lợi nhuận` (giả định 0,15).
   - Duyệt nhầm một người vỡ nợ: mất `AMT_CREDIT × tỷ lệ tổn thất` (giả định 0,60).
   - Chọn ngưỡng cho tổng chi phí thấp nhất trên dự đoán OOF. **Mọi báo cáo phải ghi rõ hai con số trên là giả định.**
3. Báo cáo kèm theo:
   - tỷ lệ duyệt tại ngưỡng đã chọn;
   - tỷ lệ vỡ nợ trong nhóm được duyệt, so với mức 8,07% chung;
   - bảng 10 nhóm điểm (decile) với tỷ lệ vỡ nợ thực tế từng nhóm.
4. **Quy ra điểm tín dụng** theo công thức `Điểm = Offset − Factor × ln(p / (1 − p))`, neo 600 điểm, cứ thêm 20 điểm thì odds tốt lên gấp đôi. Chia 5 hạng A–E.

**File cần code**

| File | Viết gì |
| --- | --- |
| `src/hcr/modeling/calibrate.py` | hiệu chỉnh isotonic, Brier trước và sau, dữ liệu cho reliability diagram |
| `src/hcr/modeling/threshold.py` | đường chi phí theo ngưỡng, ngưỡng tối ưu, bảng decile |
| `src/hcr/modeling/scorecard.py` | đổi xác suất sang điểm, chia hạng A–E |
| `configs/cost.yml` | biên lợi nhuận, tỷ lệ tổn thất, dải tìm ngưỡng |
| `configs/model.yml` (mục `calibration`, `scorecard`) | rà lại |
| `tests/unit/test_calibration.py` | Brier giảm sau hiệu chỉnh, AUC giữ nguyên |
| `tests/unit/test_scorecard.py` | 600 điểm ứng đúng odds neo, +20 điểm thì odds gấp đôi, ranh giới các hạng A–E |
| `tests/unit/test_threshold.py` | **tạo mới**: chi phí tính đúng trên ví dụ tay; ngưỡng tối ưu thay đổi đúng chiều khi đổi chi phí |

**Xong khi**
- Brier giảm sau hiệu chỉnh.
- Tỷ lệ vỡ nợ giảm dần đều từ nhóm điểm rủi ro nhất xuống nhóm an toàn nhất.
- Đã có ngưỡng, tỷ lệ duyệt và bảng decile.

> 🔒 **Cuối Task 10, đóng băng mô hình, cách hiệu chỉnh và ngưỡng.** Sau khi đã thấy số liệu holdout thì không sửa gì nữa. Sửa nghĩa là holdout không còn độc lập.

---

### Task 11 — Đánh giá cuối trên holdout

**Lệnh:** `make evaluate` · **Cần có:** Task 10 đã đóng băng

**Mục đích.** Lấy con số hiệu năng thật, trên 20% hồ sơ mô hình chưa từng thấy. Đồng thời kiểm tra mô hình có đối xử công bằng giữa các nhóm giới tính và tuổi, vì cho vay tiêu dùng chịu ràng buộc pháp lý về phân biệt đối xử.

**Cần làm**
1. **Mở holdout đúng một lần**, chấm cả hai phiên bản mô hình. Báo AUC, PR-AUC, Brier, và AUC kèm khoảng tin cậy (dự kiến khoảng ±0,008).
2. **Kiểm tra công bằng** theo giới tính và nhóm tuổi, gồm ba phép đo:
   - Tỷ lệ duyệt từng nhóm: nhóm nào bị từ chối nhiều hơn tại cùng một ngưỡng?
   - AUC từng nhóm: mô hình có chính xác đều giữa các nhóm không?
   - **Độ khớp xác suất từng nhóm**, quan trọng nhất: xác suất dự báo có khớp tỷ lệ vỡ nợ thật trong nhóm đó không? Nếu mô hình đánh giá một nhóm rủi ro hơn thực tế, nhóm đó bị thiệt một cách có hệ thống.
   - Phạm vi chỉ là **đo và công bố**, kể cả khi kết quả bất lợi. Không cần khắc phục.
3. **Giải thích mô hình** bằng SHAP trên bản `no_ext_source`: đặc trưng nào và nhóm đặc trưng nào ảnh hưởng nhiều nhất.
4. Vẽ hình cho tài liệu (reliability diagram, bảng decile) trong notebook trình bày.

**File cần code**

| File | Viết gì |
| --- | --- |
| `src/hcr/evaluation/holdout_report.py` | đọc holdout qua cơ chế một lần của Task 5, tính chỉ số, ghi MLflow |
| `src/hcr/evaluation/fairness.py` | ba phép đo công bằng theo giới tính và nhóm tuổi |
| `src/hcr/evaluation/explain.py` | SHAP tổng thể, gộp theo biến gốc và theo nhóm đặc trưng |
| `configs/model.yml` (mục `acceptance`, `fairness`) | khoảng AUC chấp nhận, định nghĩa nhóm tuổi |
| `notebooks/03_model_diagnostics.ipynb` | hình minh họa (chỉ trình bày) |
| `tests/unit/test_fairness.py` | **tạo mới**: ba phép đo tính đúng trên dữ liệu mẫu có hai nhóm biết trước kết quả |
| `tests/unit/test_holdout_report.py` | **tạo mới**: đọc lần hai mà không có `--force` thì báo lỗi |

**Xong khi**
- AUC holdout của bản `full` trong khoảng 0,74–0,80, kèm khoảng tin cậy. Nếu vượt thì phải có giải trình.
- `holdout_usage.json` chỉ có một bản ghi.
- Đã có kết quả ba phép đo công bằng.

---

### Task 12 — Kho dữ liệu cho báo cáo (bước 8)

**Lệnh:** `make mssql-up`, `make serve` · **Làm song song được với:** Task 9–10

**Mục đích.** Power BI không đọc trực tiếp ma trận 800 cột. Nó cần một bảng gọn, tên cột dễ đọc, có khóa và quan hệ rõ ràng. Task này dựng một "star schema" nhỏ (một bảng sự kiện ở giữa và các bảng danh mục xung quanh) rồi nạp vào SQL Server. **Không đưa dữ liệu thô vào SQL Server.**

Nếu Task 10 chưa xong, dùng tạm dự đoán OOF của Task 9 và thay khi có bản đã hiệu chỉnh.

**Cần làm**
1. Dựng bảng `Fact_Application`, mỗi đơn vay một dòng (307.511 dòng), gồm:
   - 9 khóa ngoại trỏ sang bảng danh mục;
   - số tiền và tỷ lệ: `AMT_CREDIT`, `AMT_ANNUITY`, `AMT_INCOME_TOTAL`, `AMT_GOODS_PRICE`, `CREDIT_INCOME_RATIO`, `ANNUITY_INCOME_RATIO`;
   - kết quả mô hình: `TARGET`, `PD_Predicted`, `CreditScore`, `Model_Version`, `IsHoldout`.
2. Dựng 9 bảng danh mục `Dim_*`:
   - `Dim_Occupation` (nghề), `Dim_Organization` (loại tổ chức), `Dim_Education` (trình độ);
   - `Dim_ContractType` (loại hợp đồng), `Dim_HousingType` (nơi ở), `Dim_FamilyStatus` (hôn nhân);
   - `Dim_AgeBand` (nhóm tuổi), `Dim_IncomeBand` (nhóm thu nhập), `Dim_RiskBand` (hạng rủi ro).

   Ba quy tắc cho bảng danh mục:
   - Khóa là số nguyên tự sinh, không dùng chuỗi làm khóa.
   - Mỗi bảng có một dòng khóa `-1` cho "không xác định", để Fact không bao giờ có khóa null.
   - Bảng có thứ tự tự nhiên (tuổi, thu nhập, hạng rủi ro, trình độ) có thêm cột `SortOrder`.
3. Chạy SQL Server trong Docker. Cổng kết nối lấy từ **một biến `MSSQL_PORT` duy nhất** trong `.env`, dùng chung cho `docker-compose`, script nạp và Power BI.
4. Nạp dữ liệu an toàn:
   - Ghi vào bảng tạm `stg_*` trước.
   - Đổi tên sang bảng thật trong **một transaction**, để Power BI không bao giờ đọc phải bảng nạp dở.
   - Sau đó mới tạo khóa chính và khóa ngoại thật.
5. Khai báo độ dài cột chuỗi theo giá trị thực tế, không đặt `NVARCHAR(4000)` cho mọi cột.

**File cần code**

| File | Viết gì |
| --- | --- |
| `src/hcr/serving/build_star.py` | dựng 9 bảng Dim và bảng Fact từ silver và dự đoán |
| `src/hcr/serving/load_sqlserver.py` | nạp vào `stg_*`, đổi tên trong transaction, tạo khóa |
| `src/hcr/serving/ddl/01_dimensions.sql` | DDL 9 bảng Dim |
| `src/hcr/serving/ddl/02_fact.sql` | DDL bảng Fact |
| `src/hcr/serving/ddl/03_constraints.sql` | khóa chính, khóa ngoại, index |
| `docker-compose.yml`, `.env.example` | SQL Server; cổng lấy từ `MSSQL_PORT` |
| `tests/gates/test_star_integrity.py` | mọi khóa ngoại trong Fact có trong Dim; Fact đúng 307.511 dòng; mỗi Dim có dòng `-1`. Phần cần SQL Server thật thì đánh dấu `@pytest.mark.integration`. |

**Xong khi**
- `Fact_Application` trong SQL Server có đúng 307.511 dòng.
- Mọi khóa ngoại đều khớp với bảng Dim, và khóa chính, khóa ngoại thật đã được tạo.
- Chạy lại `make serve` lần hai không làm hỏng bảng đang có.

---

### Task 13 — Dashboard, tài liệu và nối pipeline

**Lệnh:** `make all`, `make readme`

**Mục đích.** Trình bày kết quả cho người xem, và chứng minh toàn bộ hệ thống chạy lại được từ đầu bằng một lệnh duy nhất.

**Cần làm**

1. **Power BI: 4 trang báo cáo**, đọc trực tiếp từ SQL Server:

   | Trang | Trả lời câu hỏi | Nội dung |
   | --- | --- | --- |
   | Danh mục | Đang cho vay những ai? | số đơn, giá trị vay, tỷ lệ vỡ nợ theo loại hợp đồng, nghề, trình độ |
   | Yếu tố rủi ro | Nhóm nào rủi ro hơn? | tỷ lệ vỡ nợ theo tuổi, thu nhập, nơi ở, hôn nhân |
   | Chất lượng mô hình | Mô hình tốt đến đâu? | bảng decile, reliability diagram, AUC. **Chỉ dùng dữ liệu `IsHoldout = 1`.** |
   | Ngưỡng quyết định | Nên đặt ngưỡng ở đâu? | thanh trượt what-if, tỷ lệ duyệt và tổn thất dự kiến |

2. **Power BI: 5 measure** gồm Actual Default Rate, Average PD, Calibration Gap, Approval Rate và Application Count. Calibration Gap là measure quan trọng nhất; cắt theo giới tính và nhóm tuổi, nó chính là phép đo công bằng thứ ba.

3. **Power BI: quy tắc mô hình dữ liệu**
   - Mọi quan hệ một chiều, từ Fact sang Dim, và tạo tay chứ không để Power BI tự dò.
   - Ngưỡng viết dạng phân số (`> 0.07`, không phải `> 7`).
   - Tắt auto date/time.
   - Cột cờ và cột tỷ lệ đặt ở chế độ "không tổng hợp".

4. **README tự động.** Viết script đọc chỉ số từ MLflow rồi ghi vào README, giữa hai dòng đánh dấu. Không chép số tay. README phải nêu rõ:
   - ba giới hạn của dữ liệu: không có ngày tháng thật; xác suất không phải PD chuẩn Basel; `application_test` không có nhãn;
   - lý do không chia theo thời gian;
   - các con số chi phí là giả định.

5. **Nối pipeline.** `make all` chạy từ CSV thô đến SQL Server không cần can thiệp. CI có thêm job `pipeline-smoke` chạy toàn pipeline trên dữ liệu mẫu, và kiểm tra chạy hai lần cho manifest giống hệt nhau.

6. **Rà 14 tiêu chí nghiệm thu** ở §12 của [CLAUDE.md](CLAUDE.md) và dọn hết test còn bị skip.

**File cần code**

| File | Viết gì |
| --- | --- |
| `powerbi/` | file `.pbix` và `powerbi/README.md` hướng dẫn kết nối, danh sách measure |
| `reports/readme_fill.py` | đọc MLflow, ghi số liệu vào README giữa hai dòng đánh dấu |
| `README.md` | thêm hai dòng đánh dấu và phần giới hạn dữ liệu |
| `src/hcr/pipeline/run_all.py` | chạy tuần tự 8 bước, dừng ngay khi một gate không đạt |
| `src/hcr/pipeline/flow.py` | bản Prefect của pipeline (làm sau cùng, có thể bỏ nếu thiếu thời gian) |
| `Makefile` | target `all` gọi `run_all.py` |
| `.github/workflows/ci.yml` | thêm job `pipeline-smoke` |
| `tests/unit/test_readme_fill.py` | **tạo mới**: chỉ phần giữa hai dòng đánh dấu bị thay, phần khác giữ nguyên |

**Xong khi**
- `make all` chạy từ đầu đến cuối trên máy sạch.
- Power BI mở được đủ 4 trang.
- README có số liệu sinh tự động.
- Đạt đủ 14 tiêu chí nghiệm thu ở §12 của CLAUDE.md.
