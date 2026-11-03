# TÀI LIỆU KỸ THUẬT — HƯỚNG DẪN ĐỌC MÃ NGUỒN

Bản đồ codebase **Home Credit Default Risk** (package `hcr`)

Tài liệu này dẫn bạn đi qua từng thư mục, từng file: nó dùng để làm gì, và nó nói chuyện với phần còn lại ra sao. Bạn không cần biết lập trình để đọc phần đầu. Phần sau dành cho người sẽ mở code.

> **LƯU Ý VỀ TRẠNG THÁI REPO** (đo ngày 2026-10-28, trên nhánh `main`)
>
> Repo này đang ở giữa chừng. Phần **đã chạy thật** gồm: đóng gói dữ liệu (bước 1), kiểm hàng (bước 2), đọc cấu hình, sổ địa chỉ `paths.py`, và bộ test của các phần đó. Mọi phần còn lại là **chỗ trống**: file đã có tên hàm và docstring mô tả việc cần làm, nhưng thân hàm là `raise NotImplementedError`, còn file SQL chỉ có dòng `-- TODO`.
>
> Điều này có chủ ý. Chữ ký hàm và docstring chính là bản hợp đồng mô tả việc cần làm. Trong tài liệu này, mỗi file được ghi rõ là **thật** hay **chỗ trống**.
>
> Hai nhánh khác đang giữ công việc dở dang, chưa gộp vào `main`:
> - `task-8-baseline-metrics`: đã viết thật độ đo AUC + khoảng tin cậy, các mô hình mốc, pipeline huấn luyện.
> - `TA/clean-data-`: bản nháp bước làm sạch của đồng đội (Task 4), chưa đạt, chi tiết ở [mục 4.5](#45-silver--bước-3-làm-sạch).
>
> Đọc kèm: [CLAUDE.md](../CLAUDE.md) (luật viết code), [Đặc tả hệ thống](Đặc%20tả%20hệ%20thống%20—%20Home%20Credit%20Default%20Risk.md) (việc cần làm), [WORKLOG.md](../WORKLOG.md) (13 task và người phụ trách).

## MỤC LỤC

1. Hệ thống này làm gì?
2. Toàn cảnh trong một sơ đồ
3. Thư mục cấp cao nhất
4. `src/hcr/` — phần lớn nhất
5. `configs/` — bảng điều chỉnh
6. `data/` — kho dữ liệu theo tầng
7. `tests/` — phòng kiểm định
8. Các thư mục còn lại: `notebooks/`, `reports/`, `powerbi/`, `docs/`
9. Hạ tầng
10. Xâu chuỗi lại: một lượt chạy từ đầu đến cuối
11. Đọc tiếp từ đâu

---

## 1. Hệ thống này làm gì?

Hãy hình dung bạn là nhân viên thẩm định của một công ty cho vay tiêu dùng. Mỗi ngày có hàng nghìn đơn xin vay đổ về. Với mỗi đơn, bạn phải trả lời một câu hỏi:

> **"Nếu cho người này vay, khả năng họ không trả được nợ là bao nhiêu?"**

Làm tay thì mỗi đơn mất cả buổi: lục hồ sơ, xem họ từng vay ở đâu, trả đúng hạn hay trễ, rồi so với hàng chục nghìn người khác. Dự án này làm phần lặp đi lặp lại đó bằng dữ liệu, nhưng vẫn để con người quyết định cuối cùng.

```
Bạn đưa vào:   8 bảng dữ liệu hồ sơ vay (~58,4 triệu dòng, ~2,5 GB)

Hệ thống trả:  1. Xác suất vỡ nợ đã hiệu chỉnh cho từng đơn   (ví dụ 12%)
               2. Điểm tín dụng + hạng rủi ro A–E             (ví dụ 640 điểm, hạng B)
               3. Ngưỡng duyệt/từ chối chọn theo chi phí      (không phải 50%)
               4. Dashboard Power BI cho người quản lý xem

               -- và toàn bộ có thể chạy lại bằng một lệnh: make all
```

Điểm làm dự án này khác một bài tập học máy thông thường: **mọi con số đều kèm cách kiểm tra rằng nó không tự lừa mình.** Có chốt chặn bắt rò rỉ đáp án, có phần dữ liệu cất riêng chỉ được mở một lần, có đo công bằng theo giới tính và tuổi, và công bố cả kết quả bất lợi.

### Một con số cần nhớ: 8,07%

Trong 307.511 đơn có nhãn, chỉ 24.825 đơn vỡ nợ (8,07%). Hệ quả:

- Đoán "không ai vỡ nợ" đã đúng 91,93%. Vì vậy **accuracy bị cấm** làm thước đo.
- Không dùng ngưỡng 0,5, vì gần như không đơn nào vượt mức đó.
- Không dùng SMOTE hay bất kỳ cách sinh dữ liệu giả nào, vì chúng làm sai lệch xác suất.

### Ba giới hạn của dữ liệu (không kỹ thuật nào sửa được)

1. **Không có ngày tháng thật.** Mọi mốc thời gian là "cách ngày nộp đơn bao nhiêu ngày" (số âm). Vì thế không có phân tích theo năm hay tháng dương lịch, và không kiểm tra chéo theo thời gian được.
2. **Không biết "vỡ nợ" được định nghĩa chính xác thế nào** (ngưỡng X ngày trễ trong Y kỳ không được công bố). Xác suất đầu ra **không phải** PD theo chuẩn Basel.
3. **`application_test.csv` không có nhãn.** Mọi phép đo dựa trên phần holdout tách từ `application_train.csv`.

### Hệ thống này *không* làm gì

Không chấm điểm thời gian thực (không có API), không giám sát độ lệch dữ liệu sau triển khai, không tự động ra quyết định cho vay, không kết nối hệ thống tín dụng thật.

---

## 2. Toàn cảnh trong một sơ đồ

### 2.1 Dữ liệu đi qua tám bước

```
  data/raw/  8 file CSV gốc
      │
      ▼
  ① ingest ───────────────► data/bronze/   Parquet, nội dung y hệt CSV
      │
      ▼
  ② contracts  đủ dòng? đủ cột? khóa có trùng?        [sai: DỪNG]
      │
      ▼
  ③ silver ───────────────► data/silver/   sửa 7 bẫy giá trị, thêm cờ
      │
      ▼
  ④ split ────────────────► data/splits/   rút 20% làm holdout, ghi danh sách id
      │                                    ▲
      │   ┌────────────────────────────────┘
      │   │  BẮT BUỘC xong trước bước ⑤ (nếu đảo thứ tự: rò rỉ)
      ▼   ▼
  ⑤ features ─────────────► data/features/ 1 dòng / khách, vài trăm cột + manifest
      │
      ▼
  ⑥ quality gates  cột hỏng? cột "lộ đáp án" (AUC > 0,95)?   [sai: DỪNG]
      │
      ▼
  ⑦ modeling  mô hình mốc → LightGBM → hiệu chỉnh → ngưỡng → điểm tín dụng
      │                                                    │
      │                                                    └─► MLflow (nhật ký thí nghiệm)
      ▼
  evaluation  mở holdout ĐÚNG MỘT LẦN, đo công bằng, giải thích SHAP
      │
      ▼
  ⑧ serving ──► SQL Server (hình sao: 1 fact + 9 dim) ──► Power BI (4 trang)
```

> **Điều quan trọng nhất cần nhớ:** đây là dây chuyền **một chiều**. Mỗi bước đọc tầng dữ liệu trước và **ghi ra tầng mới**, không bao giờ ghi đè đầu vào của chính nó. Nhờ vậy chạy lại hai lần ra kết quả giống hệt từng byte, và bước nào sai thì chỉ làm lại đúng bước đó.

### 2.2 Vì sao cứ phải chia nhiều tầng như vậy?

Giống một căn bếp: nguyên liệu tươi (raw) cất vào hộp gọn (bronze), rửa sạch (silver), sơ chế thành món sẵn (features), rồi mới nấu (modeling). Nếu lỡ rửa sai, bạn rửa lại từ hộp bronze, không phải đi chợ lại. Và một đĩa mẫu (holdout) được **cất đi từ trước khi bắt đầu sơ chế**, để cuối cùng giám khảo nếm thử mà đầu bếp chưa từng thấy.

### 2.3 Vì sao tách "tính toán" khỏi "phục vụ"?

```
  DuckDB + Parquet                         SQL Server
  ─────────────────                        ──────────
  Xử lý 58 triệu dòng                      Chỉ chứa bảng nhỏ cho dashboard
  Chạy trên một máy, không cần RAM lớn     Có khóa chính, khóa ngoại, index
  Ghi ra file Parquet                      KHÔNG BAO GIỜ nhận dữ liệu thô
```

`bureau_balance` có 27,3 triệu dòng, quá lớn để xử lý bằng DataFrame thông thường. DuckDB đọc thẳng từ đĩa theo cột nên không phụ thuộc RAM. SQL Server chỉ nhận lớp kết quả cuối, vì Power BI cần một nguồn quan hệ có ràng buộc khóa.

---

## 3. Thư mục cấp cao nhất

| THƯ MỤC / FILE | DÙNG ĐỂ LÀM GÌ |
| --- | --- |
| `src/hcr/` | Toàn bộ code pipeline. Mỗi package con là một bước. |
| `configs/` | 5 file YAML chứa mọi tham số có thể muốn đổi. Code không chứa magic number. |
| `data/` | Dữ liệu theo tầng: `raw` → `bronze` → `silver` → `splits` → `features`. Bị gitignore. |
| `tests/` | Kiểm thử tự động. `unit/` kiểm từng hàm, `gates/` kiểm các chốt chặn. |
| `notebooks/` | 3 sổ nháp để khám phá và chẩn đoán. Không chứa logic pipeline. |
| `reports/` | Script tự điền số liệu vào README từ MLflow. |
| `powerbi/` | Thiết kế dashboard 4 trang (lưu dạng PBIP để diff được trong git). |
| `docs/` | Đặc tả hệ thống (`.md`, `.pdf`) và tài liệu này. |
| `Makefile` | Mỗi bước pipeline là một lệnh `make`. |
| `docker-compose.yml` | Dựng SQL Server 2022 bằng Docker. |
| `pyproject.toml`, `uv.lock` | Thư viện đã ghim phiên bản; cấu hình ruff, mypy, pytest. |
| `.env.example` | Mẫu biến môi trường: cổng, mật khẩu, địa chỉ MLflow. |
| `CLAUDE.md` | Luật viết code (xem bên dưới). |
| `WORKLOG.md` | 13 task, mỗi task ghi mục đích, việc cần làm, điều kiện "xong khi". |
| `.github/workflows/ci.yml` | Kiểm tra tự động trên GitHub mỗi lần push hoặc mở PR. |

> **Hai luật tuyệt đối trong `CLAUDE.md`, có test canh giữ tự động:**
> 1. Code viết hoàn toàn bằng tiếng Anh. Tiếng Việt chỉ nằm trong tài liệu `.md`.
> 2. Không có comment `#` ở bất kỳ file nào. Lời giải thích nằm trong docstring (Python) hoặc khóa dữ liệu `note:` / `rationale:` (YAML). Nếu một đoạn code cần comment mới hiểu được, đoạn đó phải tách thành hàm có tên tự giải thích.
>
> **Vì sao cấm comment?** Comment thường bị quên khi code đổi, rồi trở thành thông tin sai lệch. Bắt code tự giải thích bằng tên hàm giúp lời giải thích luôn đúng.

---

## 4. `src/hcr/` — phần lớn nhất

Mỗi package con ứng với một bước. Mỗi module có hàm `main()` nên chạy được bằng `python -m hcr.<package>.<module>`, và `Makefile` gọi đúng các module này.

Cột TRẠNG THÁI: **thật** = có code chạy được. **chỗ trống** = chỉ có chữ ký hàm và docstring.

### 4.1 `paths.py` và `__init__.py`

| FILE | TRẠNG THÁI | NỘI DUNG |
| --- | --- | --- |
| `paths.py` | thật | Nơi **duy nhất** biết dữ liệu mỗi tầng nằm ở đâu: `raw_path`, `bronze_path`, `ensure_parent`, `project_root`, `data_dir`, `configs_dir`… Không file nào khác tự ghép đường dẫn. |
| `__init__.py` | thật | Đánh dấu package. |

Điểm đáng chú ý: import `paths.py` không tạo thư mục nào. Thư mục chỉ được tạo khi có bước ghi file (`ensure_parent`). Docstring ghi rõ ranh giới các tầng là **ranh giới hợp đồng**: bước nào đọc tầng nào, ghi tầng nào.

### 4.2 `config/` — đọc bảng điều chỉnh

| FILE | TRẠNG THÁI | NỘI DUNG |
| --- | --- | --- |
| `models.py` | thật | 6 dataclass bất biến (`frozen=True`): `TableContract`, `DataContract`, `SilverRules`, `FeatureSpec`, `ModelConfig`, `CostConfig`. Đây là bản đã định kiểu của các file YAML. |
| `loaders.py` | thật | Các hàm `load_data_contract`, `load_silver_rules`, `load_feature_spec`… đọc YAML và dựng ra dataclass ở trên. |
| `rules.py` | thật | Kiểm luật nghiệp vụ ngoài việc đủ khóa. Ví dụ tỷ lệ holdout phải nằm trong khoảng (0, 1), tỷ lệ chi phí cũng vậy. |
| `values.py` | thật | Hàm nhỏ: `load_yaml`, `require_keys`, `strip_annotations` (bỏ các khóa giải thích `note`/`rationale`/`meta` trước khi dựng dataclass). |
| `environment.py` | thật | Đọc chuỗi kết nối SQL Server và địa chỉ MLflow **chỉ từ biến môi trường**. Không có giá trị mặc định nào được viết cứng. |

> **Vì sao dataclass bất biến?** Cấu hình đã đọc xong thì không ai được sửa giữa chừng. Nếu một bước lén đổi `random_seed`, hai lần chạy sẽ khác nhau mà không ai biết vì sao.
>
> **Vì sao thiếu khóa thì báo lỗi ngay?** Nguyên tắc "fail loud, fail early": điền giá trị mặc định âm thầm cho cấu hình sai là cách nhanh nhất để có kết quả sai mà trông như đúng.

### 4.3 `ingest/` — bước 1, đóng gói

| FILE | TRẠNG THÁI | NỘI DUNG |
| --- | --- | --- |
| `to_parquet.py` | thật | Dùng DuckDB chuyển 8 CSV sang Parquet nén. **Không sửa giá trị nào.** |

Chi tiết nhỏ nhưng đáng biết: DuckDB chỉ được phép suy kiểu thành số nguyên, số thực hoặc chữ (`TYPE_CANDIDATES`). Mặc định, nó đọc chữ `Yes`/`No` của cột `EMERGENCYSTATE_MODE` thành boolean, làm đổi nội dung mà bronze phải giữ nguyên, và bước 2 sẽ báo lỗi.

### 4.4 `contracts/` — bước 2, kiểm hàng

| FILE | TRẠNG THÁI | NỘI DUNG |
| --- | --- | --- |
| `schemas.py` | thật | Dựng schema Pandera cho từng bảng thô từ `configs/data_contract.yml`. |
| `measure.py` | thật | Đo sự thật từ file Parquet: số dòng và số cột đọc từ footer (không cần nạp cả file), khóa trùng, phân phối nhãn, độ phủ khóa ngoại. |
| `validate_raw.py` | thật | Gate bước 2: so số đo với hợp đồng. Lệch thì dừng pipeline. |

> **Vì sao tách `measure.py` và `validate_raw.py`?** `measure` chỉ **đo**, `validate_raw` chỉ **phán**. Tách ra thì test được hai việc độc lập, và gate chạy được riêng mà không cần chạy cả bước nạp dữ liệu.

### 4.5 `silver/` — bước 3, làm sạch

| FILE | TRẠNG THÁI | NỘI DUNG |
| --- | --- | --- |
| `clean_application.py` | chỗ trống | 7 hàm, mỗi hàm sửa một bẫy giá trị của bảng application (bảng bên dưới). |
| `clean_history.py` | chỗ trống | Làm sạch 6 bảng lịch sử: `XNA`/`XAP` → null, kiểm dấu `DAYS_*`, tính trước các cột hành vi (trả muộn, tỷ lệ trả đủ, mức dùng thẻ). |
| `flags.py` | chỗ trống | Cờ "có lịch sử hay không" cho từng nguồn, ví dụ `FLAG_NO_BUREAU_HISTORY`. |

**Bảy bẫy giá trị bắt buộc xử lý** (khai báo trong `configs/silver_rules.yml`):

| CỘT | VẤN ĐỀ | XỬ LÝ | GIẢI THÍCH ĐỜI THƯỜNG |
| --- | --- | --- | --- |
| `DAYS_EMPLOYED` | `365243` là mã "không đi làm" (~18%) | → null + cờ `FLAG_NO_EMPLOYMENT` | Để nguyên thì tính thâm niên trung bình ra vài trăm năm |
| `DAYS_BIRTH` | Luôn âm | Thêm `AGE_YEARS = -DAYS_BIRTH / 365.25` | Cho con người đọc được |
| `CODE_GENDER` | 4 dòng `XNA` | → null, không gán thay thế | Không đoán giới tính của ai |
| `ORGANIZATION_TYPE` | ~18% `XNA`, trùng nhóm nghỉ hưu | **Giữ** làm hạng mục riêng | Ở đây `XNA` có nghĩa thật, không phải thiếu ngẫu nhiên |
| `AMT_INCOME_TOTAL` | Có người thu nhập 117 triệu | Winsorize ở phân vị 99,9, **không xóa dòng** | Một con số cực đoan làm méo cả thống kê |
| `EXT_SOURCE_1` | Thiếu ~56% | Giữ null + cờ thiếu | Việc thiếu điểm cũng là thông tin |
| `OWN_CAR_AGE` | Thiếu ~66% (không có xe) | Giữ null, **không điền 0** | Không có xe khác với xe mới tinh |

> **Nguyên tắc xuyên suốt: thiếu dữ liệu không phải là số 0.** Sau mỗi `LEFT JOIN`, khách không có lịch sử sẽ có cột null. `BURO_AMT_CREDIT_SUM_MEAN = 0` nghĩa là *đã vay 0 đồng*; `NULL` nghĩa là *chưa từng vay ở đâu*. Điền 0 xóa mất khác biệt giữa khách hồ sơ mỏng và khách lịch sử sạch, đúng nhóm cần phân biệt nhất. LightGBM tự học hướng rẽ cho nhánh thiếu nên sự vắng mặt trở thành đặc trưng.
>
> **Tình trạng Task 4:** đồng đội đã đẩy bản nháp lên `origin/TA/clean-data-`. Bản nháp chưa đạt: `clean_history.py` và `flags.py` vẫn là chỗ trống; các file `clean_*.py` là script chạy ở cấp module (không phải hàm import được) và có comment `#`; `CODE_GENDER` bị đổi thành `"Unknown"` thay vì null; chưa có winsorize, `AGE_YEARS`, `FLAG_NO_EMPLOYMENT`; thư mục `data/silver/` đang rỗng.

### 4.6 `split/` — bước 4, cất đĩa mẫu

| FILE | TRẠNG THÁI | NỘI DUNG |
| --- | --- | --- |
| `make_holdout.py` | chỗ trống | Gồm `stratified_split`, `assert_disjoint`, `assert_rate_parity`, `write_holdout_ids`, `load_holdout_ids`. |

Rút 20% `SK_ID_CURR` (61.502 đơn), **phân tầng theo `TARGET`** để tỷ lệ vỡ nợ hai tập lệch dưới 0,1 điểm phần trăm. Danh sách id ghi ra `data/splits/holdout_ids.parquet` và được dùng lại mọi lần chạy sau.

> **Vì sao phải xong trước bước 5?** Đây là ràng buộc thứ tự **duy nhất** không được đảo. Nếu tổng hợp đặc trưng trên toàn bộ khách rồi mới chia holdout, thông tin của holdout đã lọt vào đặc trưng. Triệu chứng là AUC lúc CV cao hơn AUC holdout khoảng 0,02–0,05, một khoảng chênh đủ nhỏ để bị nhầm là dao động bình thường.

### 4.7 `features/` — bước 5, sơ chế

| FILE | TRẠNG THÁI | NỘI DUNG |
| --- | --- | --- |
| `build.py` | chỗ trống | Điều phối: đọc `features.yml`, sinh SQL, chạy trên DuckDB qua hai tầng (`fold_stage_one`, `fold_stage_two`), gộp thành ma trận và ghi manifest. |
| `select.py` | chỗ trống | Lọc cột theo tiêu chí **cố định trước khi xem kết quả**: trên 95% null, một giá trị duy nhất, hoặc `\|r\| > 0,98` với cột khác. |
| `sql/application_ratios.sql` | chỗ trống | Sáu tỷ lệ bắt buộc, mỗi mẫu số có chặn chia cho 0. |
| `sql/bureau_balance_agg.sql` | chỗ trống | Tầng 1: gộp 27,3 triệu dòng về `SK_ID_BUREAU`. |
| `sql/bureau_agg.sql` | chỗ trống | Tầng 2: `LEFT JOIN` kết quả tầng 1 vào `bureau`, gộp về `SK_ID_CURR`. |
| `sql/previous_agg.sql` | chỗ trống | Gộp đơn vay cũ về khách hàng; cũng là cầu nối cho ba bảng tầng ba. |
| `sql/pos_cash_agg.sql` | chỗ trống | `POS_CASH_balance` → `SK_ID_PREV` → `SK_ID_CURR`. |
| `sql/installments_agg.sql` | chỗ trống | Như trên, cho từng lần trả góp: số ngày trả muộn, tỷ lệ trả đủ. |
| `sql/credit_card_agg.sql` | chỗ trống | Như trên, cho thẻ tín dụng. |

**Vì sao phải gộp hai tầng:**

```
  bureau_balance ──(gộp về SK_ID_BUREAU)──► bureau ──(gộp về SK_ID_CURR)──┐
   27,3 triệu dòng                          1,7 triệu                       │
                                                                            ▼
  POS_CASH_balance ───┐                                              application_train
  installments ───────┼──(gộp về SK_ID_PREV)──► previous_application ──►  307.511 khách
  credit_card_balance ┘                           1,7 triệu   (gộp về SK_ID_CURR)
```

Không bảng lịch sử nào nối thẳng vào tờ đơn. Ba bảng ở tầng ba chỉ có `SK_ID_PREV`, nên phải gộp về đơn vay cũ trước, rồi mới gộp về khách.

**Bốn họ đặc trưng** (tổng khoảng 500–800 cột): tỷ lệ trên đơn hiện tại (10–15), tổng hợp toàn lịch sử (250–350), tổng hợp theo cửa sổ 3/6/12/24 tháng (150–250), và xu hướng số dư (20–40).

> **Vì sao cửa sổ thời gian quan trọng?** Hành vi trả nợ 3 tháng gần nhất mang nhiều thông tin hơn hành vi 4 năm trước. Tổng hợp toàn lịch sử làm loãng hai tín hiệu vào nhau. Đây là họ đặc trưng giá trị cao nhất và hay bị bỏ qua.
>
> **Vì sao mọi phép nối là `LEFT JOIN`?** Chỉ khoảng 48% khoản vay ngoài có dòng trong `bureau_balance`. `INNER JOIN` sẽ làm rơi hơn nửa lịch sử bureau.
>
> **Hai cấu hình song song:** `full` (có ba điểm `EXT_SOURCE_*` của bên thứ ba) và `no_ext_source` (không có). Chỉ cấu hình thứ hai dùng được cho phân tích nghiệp vụ, vì chỉ nó cho thấy thuộc tính nào của khách thực sự liên quan đến rủi ro.

### 4.8 `quality/` — bước 6, bếp trưởng soát

| FILE | TRẠNG THÁI | NỘI DUNG |
| --- | --- | --- |
| `feature_gates.py` | chỗ trống | Chốt cấu trúc: đúng số dòng, không cột toàn null, không cột hằng, không giá trị vô cực, không cặp cột tương quan quá trần. |
| `leakage_checks.py` | chỗ trống | **AUC đơn biến** (`run_univariate_gate`): mỗi cột chấm AUC riêng, vượt 0,95 thì dừng và điều tra. **Bỏ đặc trưng** (`run_ablation`): huấn luyện lại sau khi loại lần lượt 5 đặc trưng mạnh nhất. |

> **Vì sao 0,95?** Cả ba `EXT_SOURCE_*` cộng lại chỉ đạt khoảng 0,70. Một cột đơn lẻ vượt 0,95 trong bài toán rủi ro tín dụng gần như chắc chắn là rò rỉ hoặc sao chép nhãn, không phải phát hiện có giá trị. Đây là lớp phòng thủ quan trọng nhất của dự án.

### 4.9 `modeling/` — bước 7, nấu

| FILE | TRẠNG THÁI | NỘI DUNG |
| --- | --- | --- |
| `pipeline.py` | chỗ trống (*) | Dựng `sklearn.pipeline.Pipeline` cho LightGBM và logistic. Mọi imputer, scaler, encoder nằm trong Pipeline. |
| `baselines.py` | chỗ trống (*) | Ba mô hình mốc: hằng số theo tỷ lệ nền; logistic chỉ `EXT_SOURCE_*`; logistic với application + tỷ lệ. |
| `train.py` | chỗ trống (*) | LightGBM CV 5 fold cho hai cấu hình `full` và `no_ext_source`. Báo động rò rỉ nếu AUC vượt 0,85. |
| `calibrate.py` | chỗ trống | Hiệu chỉnh xác suất bằng isotonic regression trên fold riêng; Brier score và reliability diagram. |
| `threshold.py` | chỗ trống | Chọn ngưỡng theo chi phí trong `cost.yml`; dựng bảng decile. |
| `scorecard.py` | chỗ trống | Quy xác suất ra điểm: `Score = Offset − Factor·ln(p/(1−p))`, neo 600, odds nhân đôi mỗi 20 điểm; chia hạng A–E cho `Dim_RiskBand`. |

(*) Trên nhánh `task-8-baseline-metrics`, `pipeline.py` và `baselines.py` đã viết thật; `train.py` mới viết xong `stratified_folds`. Hàm `load_training_split` còn chặn vì phụ thuộc bước 3 và 4.

**Trình tự mô hình bắt buộc, từ đơn giản đến phức tạp:**

| # | MÔ HÌNH | MỤC ĐÍCH | AUC THAM CHIẾU |
| --- | --- | --- | --- |
| 0 | Hằng số theo tỷ lệ nền | Mốc chặn dưới | 0,500 |
| 1 | Logistic chỉ `EXT_SOURCE_*` | Điểm bên thứ ba mạnh đến đâu | ~0,70 |
| 2 | Logistic với application + tỷ lệ | Mốc giải thích được | ~0,74 |
| 3 | LightGBM toàn bộ đặc trưng | **Mô hình chính** | 0,78–0,79 |
| 4 | LightGBM không `EXT_SOURCE_*` | Tín hiệu nội bộ | ~0,74 |

> **AUC là gì?** Chọn ngẫu nhiên một người vỡ nợ và một người không vỡ nợ; AUC là xác suất mô hình chấm người vỡ nợ rủi ro hơn. 0,5 là đoán bừa, 1,0 là hoàn hảo. Khoảng hợp lý ở bài toán này là **0,74–0,80**. **Vượt 0,85 là cảnh báo rò rỉ**, hệ thống dừng lại thay vì ăn mừng.
>
> **Vì sao toàn bộ biến đổi phải nằm trong `Pipeline`?** Đây là ràng buộc kỹ thuật mà cả thiết kế huấn luyện dựa vào. Ba trong năm nguồn rò rỉ (target encoding ngoài fold, điền thiếu bằng thống kê toàn tập, chuẩn hóa trên toàn tập) bị chặn bởi *cấu trúc* chứ không phải bởi kỷ luật con người: khi phép biến đổi là một bước của Pipeline, nó chỉ được fit trong phần train của từng fold.
>
> **Vì sao hiệu chỉnh?** Dùng class weight để bù mất cân bằng làm xác suất lệch cao. Quyết định cấp tín dụng cần xác suất đúng thang đo, không chỉ đúng thứ hạng. Sau hiệu chỉnh, khi mô hình nói "10%" thì trong 100 người như vậy khoảng 10 người vỡ nợ thật. Lưu ý: AUC không đổi sau hiệu chỉnh vì thứ hạng không đổi, nên dùng AUC để kiểm tra hiệu chỉnh là sai. Phải dùng Brier score và reliability diagram.
>
> **Ngưỡng chọn thế nào?** Từ chối nhầm người tốt mất `AMT_CREDIT × 0,15` (biên lợi nhuận). Duyệt nhầm người vỡ nợ mất `AMT_CREDIT × 0,60` (tỷ lệ tổn thất). Hai tỷ lệ này là **giả định**, nằm trong `configs/cost.yml`, và mọi báo cáo phải nói rõ điều đó.

### 4.10 `evaluation/` — chấm điểm cuối

| FILE | TRẠNG THÁI | NỘI DUNG |
| --- | --- | --- |
| `metrics.py` | chỗ trống (*) | AUC, PR-AUC, Brier, log loss, `decile_lift`, `calibration_gap`. Accuracy bị cấm có chủ đích. |
| `confidence.py` | chỗ trống (*) | Khoảng tin cậy AUC theo Hanley–McNeil; bootstrap làm phương án dự phòng. |
| `holdout_report.py` | chỗ trống | Mở holdout đúng một lần, ghi `holdout_usage.json`. |
| `fairness.py` | chỗ trống | Ba phép đo theo giới tính và nhóm tuổi: tỷ lệ duyệt, AUC theo nhóm, độ hiệu chỉnh theo nhóm. |
| `explain.py` | chỗ trống | SHAP `TreeExplainer` ở hai mức: toàn danh mục và từng hồ sơ. |

(*) Trên nhánh `task-8-baseline-metrics`: `compute_metrics` và phần Hanley–McNeil đã viết thật; còn thiếu `decile_lift`, `calibration_gap`, `bootstrap_auc_interval`.

> **Vì sao holdout chỉ mở một lần?** Docstring của `holdout_report.py` giải thích rất thẳng: holdout giữ được tính độc lập *chỉ khi nó không dùng để ra bất kỳ quyết định nào*. Sau nhiều thí nghiệm, điểm CV trôi dần lên lạc quan vì các lựa chọn đã được chọn để hợp với nó. Holdout là ước lượng duy nhất không bị như vậy, cho đến lúc một kết quả từ nó làm bạn đổi cái gì đó. Module này cố ý "khó chạy lần hai": lần đầu ghi một dòng vào sổ, lần sau phải kèm `--force` và lý do, lý do cũng được ghi lại. Cơ chế này không phải bảo mật; nó là gờ giảm tốc chống thói quen có thật: nhìn holdout, không thích con số, chỉnh một thứ, nhìn lại.
>
> **Vì sao mọi AUC phải kèm khoảng tin cậy?** Holdout có 4.964 ca dương, cho sai số chuẩn khoảng 0,004 quanh AUC 0,78, tức khoảng tin cậy 95% xấp xỉ 0,772–0,788. Khoảng này đủ để phân biệt hai mô hình chênh 0,01 AUC. Một AUC trần trụi mời gọi những so sánh mà khoảng tin cậy sẽ từ chối.
>
> **Đo công bằng:** dữ liệu có `CODE_GENDER` và `DAYS_BIRTH`, mà cho vay tiêu dùng chịu ràng buộc pháp lý về phân biệt theo giới và tuổi. Phép đo quan trọng nhất là độ hiệu chỉnh theo nhóm: nếu mô hình ước lượng rủi ro của một nhóm cao hơn thực tế, nhóm đó bị định giá bất lợi một cách có hệ thống dù rủi ro thật tương đương. Phạm vi dừng ở đo và báo cáo, nhưng **kết quả phải công bố kể cả khi bất lợi.**

### 4.11 `serving/` — bước 8, bày đĩa

| FILE | TRẠNG THÁI | NỘI DUNG |
| --- | --- | --- |
| `build_star.py` | chỗ trống | Dựng `Fact_Application` và 9 bảng dimension (`build_dimension`, `build_age_bands`, `build_income_bands`). |
| `load_sqlserver.py` | chỗ trống | Nạp vào bảng `stg_*`, đổi tên trong **một transaction**, rồi tạo khóa chính và khóa ngoại. Kèm hai gate: toàn vẹn khóa ngoại và số dòng fact. |
| `ddl/01_dimensions.sql` | chỗ trống | Tạo 9 bảng `Dim_*`. |
| `ddl/02_fact.sql` | chỗ trống | Tạo `Fact_Application`. |
| `ddl/03_constraints.sql` | chỗ trống | Tạo `PRIMARY KEY` / `FOREIGN KEY` thật, sau khi đổi tên. |

```
                      Dim_Occupation (19)   Dim_Organization (59)   Dim_Education (6)
                              \                    |                    /
  Dim_ContractType (3) ──────  ─────  Fact_Application  ─────  ────── Dim_HousingType (7)
                                       307.511 đơn vay
  Dim_FamilyStatus (7) ──────  ─────  9 khóa ngoại      ─────  ────── Dim_AgeBand (7)
                              /        6 measure                \
                  Dim_IncomeBand (6)   TARGET, PD_Predicted,      Dim_RiskBand (6)
                                       CreditScore, IsHoldout
```

(Số trong ngoặc là số dòng dự kiến, đã cộng một dòng "không xác định" cho mỗi dimension.)

> **Ba quy tắc dimension:** khóa là số nguyên tự sinh (không dùng chuỗi nghiệp vụ làm khóa); mỗi dimension có một dòng khóa `-1` cho giá trị không xác định để fact không bao giờ có khóa ngoại null; dimension có thứ tự tự nhiên (tuổi, thu nhập, rủi ro, học vấn) có cột `SortOrder`.
>
> **Vì sao `TARGET` và `PD_Predicted` nằm cạnh nhau trong cùng fact?** Có chủ đích: cho phép dashboard đo chất lượng chính mô hình, không chỉ mô tả danh mục.
>
> **Vì sao nạp qua bảng tạm rồi đổi tên?** Để bảng đích không bao giờ ở trạng thái dở dang khi Power BI đang đọc. Nếu bước đổi tên hỏng giữa chừng, transaction quay lui và dashboard vẫn phục vụ bản cũ bình thường.
>
> **Vì sao không đặt mọi cột chuỗi là `NVARCHAR(4000)`?** Vượt giới hạn khóa 1700 byte nên không tạo index được. Độ dài cột khai báo theo giá trị thực tế (`infer_string_column_length`).

### 4.12 `pipeline/` — quản đốc

| FILE | TRẠNG THÁI | NỘI DUNG |
| --- | --- | --- |
| `flow.py` | chỗ trống | Danh sách 8 bước kèm gate (`PipelineStep`, `STEP_ORDER`), và `assert_ordering` kiểm hằng `CRITICAL_ORDERING = (4, 5)`. |
| `run_all.py` | chỗ trống | Lệnh duy nhất chạy lại mọi thứ từ CSV thô (`make all`). |

Docstring của `flow.py` ghi quyết định điều phối: **Makefile trước, Prefect sau.** Yêu cầu là một lệnh chạy lại tất cả; bộ lập lịch chỉ đáng thêm khi pipeline chạy không người trông.

---

## 5. `configs/` — bảng điều chỉnh

Năm file YAML. Mọi giải thích đi theo khóa `meta:` / `note:` / `rationale:` (đọc như comment nhưng parse được, nên test khẳng định được).

| FILE | TRẠNG THÁI | NỘI DUNG |
| --- | --- | --- |
| `data_contract.yml` | thật | Hợp đồng dữ liệu thô: số dòng, số cột, dtype, khóa chính của từng bảng; độ phủ khóa ngoại kỳ vọng; phân phối `TARGET`. Bước 2 so dữ liệu với file này. |
| `silver_rules.yml` | thật | Sentinel `365243`, các mã thiếu, dấu cột `DAYS_*`, cột suy diễn, cột chuyển null, cột giữ `XNA` làm hạng mục, winsorize, cờ thiếu, cờ có lịch sử. |
| `features.yml` | thật | Danh sách cột × phép tổng hợp từng bảng nguồn; cửa sổ `[3, 6, 12, 24]` tháng; sáu tỷ lệ; hai cấu hình `full` / `no_ext_source`; tiêu chí lọc. SQL bước 5 sinh từ file này. |
| `model.yml` | thật | `random_seed: 42`, tỷ lệ holdout, 5 fold, class weight, ba mô hình mốc, siêu tham số LightGBM, hiệu chỉnh, quy đổi điểm, ngưỡng nghiệm thu AUC, MLflow, nhóm công bằng. |
| `cost.yml` | thật | Cấu trúc chi phí giả định: `profit_margin: 0.15`, `loss_given_default: 0.60`, lưới tìm ngưỡng. |

> **Vì sao danh sách cột × phép tổng hợp nằm trong YAML chứ không dùng vòng lặp quét hết cột?** Quét hết sẽ sinh ra cột vô nghĩa (ví dụ độ lệch chuẩn của một cờ nhị phân không mang thông tin) và làm số chiều nổ ra. Khai báo tường minh buộc người viết trả lời "vì sao cột này cần phép tổng hợp này".

---

## 6. `data/` — kho dữ liệu theo tầng

Toàn bộ `data/` bị gitignore (CSV và Parquet không bao giờ vào git).

| THƯ MỤC | BƯỚC TẠO RA | NỘI DUNG | HIỆN TẠI |
| --- | --- | --- | --- |
| `raw/` | tải từ Kaggle | 8 file CSV + `HomeCredit_columns_description.csv`. Thư mục con `home-credit-default-risk/` chứa `application_train/test.csv`. | có đủ |
| `bronze/` | ① | 8 file Parquet nén, nội dung y hệt CSV. | có đủ, đúng số dòng |
| `silver/` | ③ | Mỗi bảng nguồn một bảng sạch, **số dòng không đổi**. | rỗng |
| `splits/` | ④ | `holdout_ids.parquet` và sổ `holdout_usage.json`. | rỗng |
| `features/` | ⑤ | Ma trận huấn luyện (một dòng một `SK_ID_CURR`) + manifest. | rỗng |

> **Manifest là gì?** Mỗi phiên bản ma trận đặc trưng đi kèm một file ghi: danh sách cột, phép tổng hợp sinh ra từng cột, và hash dữ liệu nguồn. Không có manifest thì một cột như `BURO_AMT_CREDIT_SUM_MEAN` không truy ngược được về cách tính.
>
> **Quy ước đặt tên cột đặc trưng:** `<NGUỒN>_<CỘT>_<PHÉP>` (ví dụ `BURO_AMT_CREDIT_SUM_MEAN`), có cửa sổ thì thêm `_<N>M` (ví dụ `INST_DPD_MEAN_3M`). Tiền tố nguồn chỉ có bảy loại: `APP_`, `BURO_`, `BB_`, `PREV_`, `POS_`, `INST_`, `CC_`. Cột cờ bắt đầu bằng `FLAG_`.

---

## 7. `tests/` — phòng kiểm định

Test **không chạm dữ liệu thật** (2,5 GB làm bộ test chậm đến mức không ai chạy, và gate không được chạy thì vô dụng). Dữ liệu mẫu dựng trong `conftest.py`: vài chục dòng mỗi bảng, **cố ý chứa sẵn các bẫy giá trị**, vì test "sentinel được xử lý" sẽ đậu dễ dàng trên dữ liệu không có sentinel.

| FILE | TRẠNG THÁI | KIỂM TRA GÌ |
| --- | --- | --- |
| `conftest.py` | thật | Fixture cho 7 bảng (`application_frame`, `bureau_frame`…), `predictions_and_labels`, `duckdb_connection`. Có hai hook biến test còn là khung (`NotImplementedError`) thành "skipped" thay vì "failed", nên CI vẫn xanh nhưng `-ra` vẫn liệt kê từng test chưa viết. |
| `fixtures/README.md` | thật | Giải thích từng bẫy trong fixture và lý do cần có. |
| `unit/test_fixtures.py` | thật | Fixture có đủ các bẫy như đã hứa. |
| `unit/test_source_rules.py` | thật | Thực thi hai luật tuyệt đối trên toàn repo: không comment `#` (cả Python lẫn file cấu hình), không chữ cái ngoài tiếng Anh trong code. |
| `unit/test_paths.py` | thật | Mọi đường dẫn đến từ `hcr.paths`. |
| `unit/test_config.py` | thật | 5 YAML đọc được; thiếu khóa thì báo lỗi to. |
| `unit/test_ingest.py` | thật | Bronze là CSV đổi định dạng, nội dung không đổi. |
| `unit/test_contract_measure.py` | thật | Số đo bước 2: footer, khóa trùng, nhãn, độ phủ. |
| `unit/test_contract_schemas.py` | thật | Schema Pandera và tính nhất quán của hợp đồng thật. |
| `gates/test_contract_raw.py` | thật | Gate bước 2: một ca đạt, một ca trượt cho mỗi điều kiện. |
| `unit/test_silver_rules.py` | chỗ trống | Mỗi bẫy trong 7 bẫy một test riêng, cả hai nhánh. |
| `unit/test_features_sql.py` | chỗ trống | Số dòng sau join, xử lý null, chặn chia cho 0. |
| `unit/test_calibration.py` | chỗ trống | Hiệu chỉnh không làm đổi thứ hạng. |
| `unit/test_scorecard.py` | chỗ trống | Công thức quy điểm và dải rủi ro. |
| `gates/test_split_disjoint.py` | chỗ trống | Gate bước 4: hai tập không giao nhau, tỷ lệ vỡ nợ cân bằng. |
| `gates/test_feature_gates.py` | chỗ trống | Gate bước 6, gồm AUC đơn biến. |
| `gates/test_star_integrity.py` | chỗ trống | Gate bước 8: mọi khóa ngoại tồn tại, fact đủ 307.511 dòng. |

> **Quy ước:** test mirror cấu trúc `src/`; mỗi test kiểm một hành vi và tên mô tả hành vi (`test_days_employed_sentinel_becomes_null`, không phải `test_normalize_1`); mỗi gate có test cho cả nhánh đạt và nhánh trượt.
>
> **Hai nhãn đặc biệt:** `@pytest.mark.integration` cho test cần SQL Server chạy thật, `@pytest.mark.slow` cho test chạy trên toàn bộ dữ liệu. CI bỏ qua cả hai.
>
> **Vì sao test "còn là khung" được tính là skipped chứ không phải failed?** Nếu để đỏ, CI đỏ vĩnh viễn và một lỗi thật bị chìm giữa hàng trăm lỗi dự kiến. Skipped giữ CI xanh, còn `-ra` vẫn liệt kê từng test chưa viết nên công việc dở dang không bị lãng quên.

---

## 8. Các thư mục còn lại

### 8.1 `notebooks/`

| FILE | NỘI DUNG |
| --- | --- |
| `01_eda_application.ipynb` | Khám phá bảng application, xác nhận 7 bẫy có thật với đúng tỷ lệ. |
| `02_eda_history_tables.ipynb` | Khám phá 6 bảng lịch sử. |
| `03_model_diagnostics.ipynb` | Chẩn đoán mô hình sau huấn luyện. |

Notebook chỉ để khám phá và trình bày. Đoạn code nào cần chạy lại phải chuyển vào `src/`.

### 8.2 `reports/`

| FILE | TRẠNG THÁI | NỘI DUNG |
| --- | --- | --- |
| `readme_fill.py` | chỗ trống | Đọc chỉ số từ MLflow, ghi vào `README.md` giữa hai dòng đánh dấu `<!-- BEGIN GENERATED METRICS -->` và `<!-- END GENERATED METRICS -->`. Sinh bảng trình tự mô hình, phần ba giới hạn dữ liệu, phần công bằng. |

> **Vì sao tự sinh số liệu?** Tài liệu cập nhật tay sẽ lệch khỏi code ở lần chạy kế tiếp, và sự lệch không nhìn thấy được vì con số cũ trông hợp lý y như con số mới. Script thay khối giữa hai dòng đánh dấu xóa hẳn khả năng đó.

### 8.3 `powerbi/`

Chỉ có `README.md` thiết kế (chưa có file báo cáo). Bốn trang:

| TRANG | CÂU HỎI | NỘI DUNG |
| --- | --- | --- |
| Danh mục | Cơ cấu đơn vay? | Số đơn, giá trị, tỷ lệ vỡ nợ theo loại hợp đồng, nghề, trình độ |
| Yếu tố rủi ro | Nhóm nào rủi ro hơn? | Theo nhóm tuổi, thu nhập, cư trú, hôn nhân |
| Chất lượng mô hình | Mô hình tốt đến đâu? | Bảng decile, reliability diagram, AUC trên holdout |
| Ngưỡng quyết định | Nên đặt ngưỡng ở đâu? | Tham số what-if, tỷ lệ duyệt và tổn thất dự kiến |

> **Bốn quy tắc mô hình ngữ nghĩa:** mọi quan hệ một chiều từ fact sang dimension (hai chiều làm mẫu số của measure tỷ lệ bị lọc theo điều kiện tử số, ra 100%); quan hệ tạo thủ công, không auto-detect; ngưỡng DAX viết dạng phân số (`> 0.07`, không phải `> 7`); tắt auto date/time (dữ liệu không có cột ngày nào).
>
> **Trang Chất lượng mô hình chỉ đọc dữ liệu có `IsHoldout = 1`**, phần duy nhất mô hình chưa từng thấy. Bỏ bộ lọc này là cách báo cáo hiệu năng in-sample như thể out-of-sample.
>
> **Measure quan trọng nhất là Calibration Gap** (`Average PD − Actual Default Rate`). Cắt theo giới tính và nhóm tuổi, chính measure này thực hiện phép kiểm tra công bằng thứ ba.

### 8.4 `docs/`

| FILE | NỘI DUNG |
| --- | --- |
| `Đặc tả hệ thống — Home Credit Default Risk.md` / `.pdf` | Nguồn chân lý về nghiệp vụ: hệ thống cần làm gì. |
| `PROJECT_STRUCTURE.md` | Tài liệu này. |

---

## 9. Hạ tầng

### 9.1 `Makefile`

| LỆNH | BƯỚC | MODULE CHẠY |
| --- | --- | --- |
| `make install` | | `uv sync --locked` |
| `make ingest` | ① | `hcr.ingest.to_parquet` |
| `make contracts` | ② | `hcr.contracts.validate_raw` |
| `make silver` | ③ | `clean_application`, rồi `clean_history` |
| `make split` | ④ | `hcr.split.make_holdout` |
| `make features` | ⑤ | `hcr.features.build`, rồi `select` |
| `make gates` | ⑥ | `feature_gates`, rồi `leakage_checks` |
| `make train` | ⑦ | `baselines` → `train` → `calibrate` → `threshold` → `scorecard` |
| `make evaluate` | | `holdout_report`, `fairness`, `explain` |
| `make serve` | ⑧ | `build_star`, rồi `load_sqlserver` |
| `make readme` | | `reports.readme_fill` |
| `make all` | ①–⑧ | `hcr.pipeline.run_all` |
| `make check` | | `lint` + `typecheck` (`mypy src/hcr`) + `test` |
| `make mssql-up` / `mssql-down` | | Bật / tắt SQL Server trong Docker |
| `make clean` | | Xóa `data/bronze`, `silver`, `features`, `splits` |

### 9.2 `docker-compose.yml`

Một dịch vụ duy nhất: `mssql` (SQL Server 2022, bản Developer), container `hcr-mssql`, có healthcheck chạy `SELECT 1` và một volume giữ dữ liệu.

> **Hai chi tiết đáng chú ý:**
> - `MSSQL_SA_PASSWORD` và `MSSQL_PORT` đều dùng cú pháp `${VAR:?thông báo}`: thiếu biến trong `.env` thì Compose **từ chối khởi động** thay vì chạy với giá trị mặc định.
> - Cổng được đọc từ **một biến môi trường duy nhất**, dùng chung cho Compose, script nạp và chuỗi kết nối Power BI. Lệch cổng giữa ba nơi là lỗi thường gặp và khó phát hiện.

### 9.3 `.github/workflows/ci.yml`

| JOB | KIỂM TRA | TRẠNG THÁI |
| --- | --- | --- |
| `lint` | `ruff format --check`, `ruff check`, `mypy src/hcr` | thật |
| `source-rules` | `pytest tests/unit/test_source_rules.py` (không comment `#`, chỉ tiếng Anh) | thật |
| `test` | `pytest -m "not integration and not slow"` kèm độ phủ | thật |
| `pipeline-smoke` | Chạy bước 1–7 trên dữ liệu fixture, chạy hai lần so manifest từng byte | chỗ trống (chỉ in `TODO`, `exit 0`) |

### 9.4 `pyproject.toml`, `uv.lock`, `.env.example`

- **`pyproject.toml`**: Python `==3.12.*`; mọi thư viện ghim phiên bản chính xác (`duckdb==1.1.3`, `polars==1.17.1`, `lightgbm==4.5.0`, `scikit-learn==1.6.0`, `shap==0.46.0`, `mlflow==2.19.0`, `pandera==0.22.1`…). `pytest` chạy với `--strict-markers`. Ruff bật rule `ERA` (bắt code bị comment) và `T20` (chặn `print`) để thực thi luật tự động; `mypy` ở mức strict cho `src/`.
- **`uv.lock`**: khóa chính xác cả cây phụ thuộc. Máy khác cài ra y hệt.
- **`.env.example`**: `MSSQL_PORT`, `MSSQL_SA_PASSWORD`, `MSSQL_HOST`, `MSSQL_DATABASE`, `MLFLOW_TRACKING_URI`, `MLFLOW_EXPERIMENT_NAME`. Chép thành `.env` và điền. `.env` thật không bao giờ commit.

> **Công nghệ đã bị loại, không đề xuất lại:** Spark (58 triệu dòng chạy được trên một máy, thêm JVM mà không thêm năng lực), Airflow (chi phí vận hành vượt nhu cầu pipeline batch một người), SMOTE và biến thể (phá hiệu chỉnh xác suất), mạng nơ-ron (trên dữ liệu bảng cỡ này gradient boosting tốt hơn với chi phí thấp hơn).

---

## 10. Xâu chuỗi lại: một lượt chạy từ đầu đến cuối

```
 1. Bạn đặt 8 file CSV vào data/raw/
 2. make ingest         đóng gói thành Parquet ở data/bronze/
 3. make contracts      so với data_contract.yml: lệch → DỪNG
 4. make silver         sửa 7 bẫy giá trị, thêm cờ → data/silver/
 5. make split          rút 20% holdout, ghi holdout_ids.parquet
                        (bắt buộc TRƯỚC bước kế tiếp)
 6. make features       DuckDB gộp 58 triệu dòng thành 1 dòng / khách,
                        ghi ma trận + manifest → data/features/
 7. make gates          cột toàn null / hằng / vô cực / AUC đơn biến > 0,95 → DỪNG
 8. make train          a. ba mô hình mốc, ghi MLflow
                        b. LightGBM CV 5 fold, hai cấu hình
                           AUC > 0,85? → DỪNG, điều tra rò rỉ
                        c. hiệu chỉnh isotonic trên fold riêng
                        d. chọn ngưỡng theo chi phí, bảng decile
                        e. quy ra điểm tín dụng, chia hạng A–E
 9. make evaluate       mở holdout ĐÚNG MỘT LẦN (ghi sổ), đo AUC kèm khoảng
                        tin cậy, bảng decile, 3 phép công bằng, SHAP
10. make mssql-up       bật SQL Server
11. make serve          dựng 1 fact + 9 dim, nạp qua bảng tạm,
                        đổi tên trong một transaction, tạo khóa → hợp lệ? → DỪNG nếu không
12. Power BI            đọc trực tiếp từ SQL Server, 4 trang
13. make readme         chép số liệu từ MLflow vào README
        ── hoặc làm tất cả bằng:  make all
```

**Bốn tình huống hệ thống bắt buộc xử lý đúng** (tiêu chí nghiệm thu):

| TÌNH HUỐNG | HỆ THỐNG PHẢI LÀM GÌ |
| --- | --- |
| AUC holdout vượt 0,85 hoặc một cột đơn lẻ đạt AUC trên 0,95 | Dừng, báo người dùng, điều tra rò rỉ. Không coi là tin vui. |
| Chạy `make all` hai lần liên tiếp | Hai lần ra kết quả giống hệt từng byte; không bước nào ghi đè đầu vào. |
| Có người đọc nhãn holdout lần thứ hai | Từ chối, trừ khi kèm `--force` và lý do; cả hai được ghi vào `holdout_usage.json`. |
| Nạp SQL Server hỏng giữa chừng | Transaction quay lui; Power BI vẫn đọc được bản cũ nguyên vẹn. |

---

## 11. Đọc tiếp từ đâu

| BẠN MUỐN HIỂU | ĐỌC THEO THỨ TỰ |
| --- | --- |
| Dự án nhằm mục đích gì, làm gì và không làm gì | `CLAUDE.md` mục 0–2 → Đặc tả hệ thống |
| Luồng tổng thể và thứ tự các bước | `pipeline/flow.py` (docstring + `STEP_ORDER`) → `Makefile` |
| Dữ liệu thô trông thế nào, có bẫy gì | `configs/data_contract.yml` → `configs/silver_rules.yml` → `tests/conftest.py` |
| Dữ liệu được lưu ở đâu theo từng tầng | `paths.py` |
| Đặc trưng được tính thế nào | `configs/features.yml` → `features/build.py` → `features/sql/*.sql` |
| Vì sao kết quả đáng tin (chống rò rỉ) | `modeling/pipeline.py` (docstring) → `quality/leakage_checks.py` → `evaluation/holdout_report.py` |
| Mô hình được đo ra sao | `configs/model.yml` → `evaluation/metrics.py` → `evaluation/confidence.py` |
| Ngưỡng và điểm tín dụng đến từ đâu | `configs/cost.yml` → `modeling/threshold.py` → `modeling/scorecard.py` |
| Công bằng được kiểm thế nào | `evaluation/fairness.py` |
| Dashboard lấy dữ liệu từ đâu | `serving/build_star.py` → `serving/ddl/*.sql` → `powerbi/README.md` |
| Việc nào đã xong, ai đang làm gì | `WORKLOG.md` → `git branch -a` |
| Quy tắc viết code trước khi sửa bất cứ thứ gì | `CLAUDE.md` mục 3 và mục 13 (checklist trước khi báo hoàn thành) |
