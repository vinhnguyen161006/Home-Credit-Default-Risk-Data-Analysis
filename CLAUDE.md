# CLAUDE.md — Home Credit Default Risk

Hướng dẫn làm việc cho Claude Code trên repo này. Nguồn chân lý về nghiệp vụ là
[Đặc tả hệ thống — Home Credit Default Risk.md](Đặc tả hệ thống — Home Credit Default Risk.md).
File này đặc tả **cách viết code**; file đặc tả kia đặc tả **cần làm gì**. Khi hai file xung đột, dừng lại và hỏi người dùng.

---

## 0. Ba luật tuyệt đối

Ba luật này áp cho mọi file, mọi commit, không có ngoại lệ:

1. **Code hoàn toàn bằng tiếng Anh.** Tên module, hàm, biến, cột, bảng, test, commit message, docstring, log message, tên file — tất cả tiếng Anh. Tiếng Việt chỉ được xuất hiện trong tài liệu `.md` dành cho người đọc (README, file này, đặc tả) và trong phần trao đổi với người dùng.
2. **Không dùng comment `#` ở bất kỳ đâu.** Áp cho Python, YAML, Makefile, Dockerfile, `.env`, mọi loại file. Không có comment nội dòng, không có comment giải thích, không có comment chia khối, không có banner `# ====`, không có `# TODO`.
   - **Trong Python:** giải thích duy nhất được phép là **docstring** (`"""..."""`) ở đầu module, class và hàm public. Nếu một đoạn code cần comment để hiểu được, đoạn đó cần được tách thành hàm có tên tự giải thích. Việc cần làm ghi trong section `TODO:` của docstring, không ghi bằng `# TODO`.
   - **Trong YAML:** mọi giải thích là **khóa dữ liệu**, không phải comment — dùng `note:`, `rationale:`, `meta:`. Cách này vừa đọc được như comment, vừa parse được nên test khẳng định được, và không vi phạm luật. Giải thích dài thuộc về docstring của module đọc file đó.
   - **Trong SQL:** dùng `--` chỉ khi cần giải thích một thủ thuật không thể hiện qua tên; mặc định là không comment, dùng CTE có tên rõ nghĩa thay thế.
   - Ngoại lệ cú pháp duy nhất: `#!/usr/bin/env python` (shebang), `# type: ignore[...]`, `# noqa: ...` khi thực sự bắt buộc, và cú pháp Makefile/YAML không có dạng khác (ví dụ `.PHONY`).
   - Ruff rule `ERA` (phát hiện code bị comment) và `T20` (chặn `print`) đã bật trong `pyproject.toml` để thực thi luật này tự động.
3. **Không bước nào ghi đè đầu vào của chính nó.** Mọi hàm pipeline nhận đường dẫn vào và ghi ra đường dẫn mới. Chạy pipeline hai lần phải cho kết quả byte-identical.

---

## 1. Bối cảnh dự án

Hệ thống chấm điểm rủi ro vỡ nợ trên bộ dữ liệu Home Credit: 8 bảng quan hệ, ~58,4 triệu dòng.
Đầu ra gồm: xác suất vỡ nợ đã hiệu chỉnh, ngưỡng quyết định theo chi phí, và lớp báo cáo Power BI.

**Trong phạm vi:** xử lý theo lô, feature engineering, huấn luyện + hiệu chỉnh, chọn ngưỡng theo chi phí, kiểm tra công bằng, star schema BI, dashboard.

**Ngoài phạm vi — không tự ý xây:** API chấm điểm realtime, giám sát drift, hệ ra quyết định tự động, tích hợp hệ thống tín dụng thật.

### Ba giới hạn của dữ liệu (không khắc phục được bằng kỹ thuật)

- Không có ngày tháng tuyệt đối. Mọi mốc thời gian là số ngày/tháng tương đối so với ngày nộp đơn. ⇒ Không dựng date dimension, không phân tích xu hướng theo tháng dương lịch, **không time-based validation**.
- Ngưỡng X/Y của nhãn không được công bố. ⇒ Xác suất đầu ra **không** phải PD theo chuẩn Basel. Mọi tài liệu kết quả phải nói rõ điều này.
- `application_test.csv` không có nhãn. ⇒ Mọi đo lường dựa trên holdout tách từ `application_train.csv`.

---

## 2. Dữ liệu nguồn

Dữ liệu thô nằm ở `archive/` và `archive/home-credit-default-risk/`. **Không bao giờ commit CSV hoặc Parquet vào git.**

| File | Dòng | Grain | Khóa |
| --- | --- | --- | --- |
| `application_train.csv` | 307.511 | một đơn đang xét duyệt | `SK_ID_CURR` (PK) |
| `application_test.csv` | 48.744 | như trên, không có `TARGET` | `SK_ID_CURR` (PK) |
| `bureau.csv` | 1.716.428 | một khoản vay ở tổ chức khác | `SK_ID_BUREAU` (PK), `SK_ID_CURR` (FK) |
| `bureau_balance.csv` | 27.299.925 | khoản vay ngoài × tháng | `SK_ID_BUREAU` (FK) |
| `previous_application.csv` | 1.670.214 | một đơn vay trước tại Home Credit | `SK_ID_PREV` (PK), `SK_ID_CURR` (FK) |
| `POS_CASH_balance.csv` | 10.001.358 | hợp đồng POS/cash × tháng | `SK_ID_PREV` (FK) |
| `installments_payments.csv` | 13.605.401 | một lần trả góp đã thực hiện (event, không phải monthly) | `SK_ID_PREV` (FK) |
| `credit_card_balance.csv` | 3.840.312 | thẻ tín dụng × tháng | `SK_ID_PREV` (FK) |

Quan hệ ba tầng: không bảng lịch sử nào nối trực tiếp về `application_train`. Bốn bảng lớn nhất ở tầng ba ⇒ **mọi đặc trưng tầng ba phải tổng hợp hai lần**.

### Biến mục tiêu

`TARGET` nhị phân, tỷ lệ 8,07% dương (24.825 / 307.511), xấp xỉ 11,4 âm : 1 dương.

Ba hệ quả bắt buộc:

1. **Accuracy bị cấm** làm chỉ số đánh giá. Đoán tất cả 0 đạt 91,93%.
2. **Không dùng ngưỡng 0,5.** Ngưỡng chọn theo cấu trúc chi phí.
3. **Không dùng SMOTE hay bất kỳ synthetic oversampling.** Dùng `class_weight` / `scale_pos_weight`. Sinh mẫu nhân tạo phá hiệu chỉnh xác suất.

---

## 3. Luật clean code

### 3.1 Nguyên tắc nền

- **Tên thay cho comment.** Vì luật số 2 cấm comment, tên là phương tiện truyền đạt duy nhất. `aggregate_bureau_balance_to_loan_grain` tốt hơn `agg_bb` kèm một comment.
- **Một hàm làm một việc.** Hàm vượt ~40 dòng hoặc có hơn 2 mức lồng là dấu hiệu cần tách.
- **Một module một trách nhiệm.** Module vượt ~400 dòng cần tách.
- **Guard clause thay vì lồng `if`.** Thoát sớm ở điều kiện lỗi, giữ happy path ở mức thụt lề ngoài cùng.
- **Không magic number.** Mọi hằng số ngưỡng, tỷ lệ, seed khai báo ở cấp module dạng `UPPER_SNAKE_CASE`, hoặc trong YAML nếu người dùng cần đổi.
- **Không code chết.** Không giữ hàm không gọi, không giữ nhánh `if False`, không giữ import không dùng. Xóa, git đã lưu lịch sử.
- **Không catch rồi bỏ qua.** `except Exception: pass` bị cấm. Bắt đúng loại exception, hoặc để nó nổ.
- **Fail loud, fail early.** Dữ liệu sai thì raise, không âm thầm điền giá trị mặc định.

### 3.2 Quy ước đặt tên

| Loại | Quy ước | Ví dụ |
| --- | --- | --- |
| Module, package | `snake_case` | `feature_aggregation.py` |
| Hàm, biến, tham số | `snake_case` | `calibrated_probability` |
| Hàm private | `_snake_case` | `_resolve_output_path` |
| Class | `PascalCase` | `FeatureManifest` |
| Hằng số | `UPPER_SNAKE_CASE` | `HOLDOUT_FRACTION` |
| Boolean | tiền tố `is_`, `has_`, `should_` | `is_holdout`, `has_bureau_history` |
| Hàm trả về bool | tiền tố `is_`, `has_` | `has_duplicate_keys` |
| Cột đặc trưng | `<SOURCE>_<COLUMN>_<AGG>` | `BURO_AMT_CREDIT_SUM_MEAN` |
| Cột đặc trưng theo cửa sổ | `<SOURCE>_<COLUMN>_<AGG>_<N>M` | `INST_DPD_MEAN_3M` |
| Cột cờ | tiền tố `FLAG_` | `FLAG_NO_BUREAU_HISTORY` |
| Bảng BI | `Fact_*`, `Dim_*` | `Fact_Application`, `Dim_RiskBand` |
| Bảng staging SQL | `stg_*` | `stg_fact_application` |
| Test | `test_<đối tượng>_<hành vi>` | `test_days_employed_sentinel_becomes_null` |

Tiền tố nguồn cho cột đặc trưng — dùng đúng bộ này, không phát minh thêm:
`APP_`, `BURO_`, `BB_`, `PREV_`, `POS_`, `INST_`, `CC_`.

### 3.3 Type hints và docstring

Mọi hàm public có type hint đầy đủ cho tham số và giá trị trả về. Docstring theo cấu trúc một dòng mô tả + các section khi cần:

```python
def split_holdout(
    applications: pl.DataFrame,
    holdout_fraction: float,
    random_seed: int,
) -> tuple[pl.Series, pl.Series]:
    """Split application identifiers into training and holdout sets.

    Stratifies on TARGET so that the positive rate of both sets differs by
    less than HOLDOUT_STRATIFICATION_TOLERANCE percentage points. Must run
    before any aggregation step to prevent feature leakage.

    Args:
        applications: Silver-layer applications with SK_ID_CURR and TARGET.
        holdout_fraction: Share of identifiers reserved for final acceptance.
        random_seed: Seed fixing the split across runs.

    Returns:
        Training identifiers and holdout identifiers, in that order.

    Raises:
        DataContractError: If TARGET contains values outside {0, 1}.
    """
```

Docstring viết bằng tiếng Anh. Không lặp lại type trong docstring (type hint đã nói). Giải thích **vì sao**, không giải thích **cái gì** khi tên đã nói rõ.

### 3.4 Luật riêng cho pipeline

- Mỗi bước pipeline là một hàm thuần import được, nhận đường dẫn vào, trả đường dẫn ra.
- **Không I/O ẩn.** Hàm tính toán không tự đọc file; hàm orchestration đọc file rồi truyền DataFrame vào. Ngoại lệ: các hàm aggregation chạy SQL trên DuckDB nhận đường dẫn Parquet vì DuckDB đọc trực tiếp từ đĩa — đó là lý do kỹ thuật, nêu trong docstring.
- **Không state toàn cục.** Không biến module mutable, không singleton connection. DuckDB connection truyền vào như tham số hoặc tạo trong context manager.
- **Đường dẫn dùng `pathlib.Path`**, không nối chuỗi, không `os.path.join`.
- **Seed cố định ở một chỗ.** `RANDOM_SEED` khai báo trong `config/`, truyền tường minh xuống mọi hàm có tính ngẫu nhiên. Không gọi `np.random.seed()` ở cấp module.
- **Logging thay cho `print`.** Dùng `logging` ở mức module (`logger = logging.getLogger(__name__)`). Message tiếng Anh, không f-string interpolation trong call: dùng `logger.info("Wrote %s rows to %s", row_count, output_path)`.

### 3.5 Luật riêng cho SQL trên DuckDB

- Mỗi phép tổng hợp là một file `.sql` riêng trong `sql/`, không nhúng SQL dài trong chuỗi Python. Chuỗi SQL ngắn (dưới ~5 dòng) nhúng được.
- Dùng CTE có tên nghiệp vụ thay cho subquery lồng. Tên CTE là `snake_case`, mô tả grain: `balance_at_loan_grain`, `loan_at_customer_grain`.
- Từ khóa SQL viết HOA, tên bảng và cột viết như trong dữ liệu (thường HOA theo nguồn Kaggle).
- `SELECT *` bị cấm ngoài bước ingest.
- **Mọi join từ bảng cha là `LEFT JOIN`.** `INNER JOIN` làm mất hơn nửa lịch sử bureau (chỉ ~48% khoản vay ngoài có dòng trong `bureau_balance`).
- Danh sách cột × phép tổng hợp khai báo trong YAML, sinh SQL từ đó. Không vòng lặp quét toàn bộ cột.

### 3.6 Luật xử lý giá trị thiếu

Nguyên tắc chi phối toàn hệ thống: **thiếu dữ liệu không phải giá trị không.**

- Sau `LEFT JOIN`, khách không có lịch sử có cột null. **Giữ null, thêm cờ hiện diện. Không điền 0.**
- `BURO_AMT_CREDIT_SUM_MEAN = 0` nghĩa là đã vay 0 đồng; `NULL` nghĩa là chưa từng vay ở đâu. Điền 0 xóa mất phân biệt giữa khách hồ sơ mỏng và khách lịch sử sạch — đúng nhóm bài toán cần phân biệt nhất.
- LightGBM học hướng rẽ của nhánh thiếu, nên sự vắng mặt trở thành đặc trưng.
- Mọi imputer (nếu dùng cho baseline logistic regression) **phải nằm trong `sklearn.pipeline.Pipeline`**, fit trong fold.

Bảy bẫy giá trị phải xử lý ở lớp silver — bắt buộc, không tùy chọn:

| Trường | Vấn đề | Xử lý |
| --- | --- | --- |
| `DAYS_EMPLOYED` | `365243` là sentinel cho người không đi làm (~18%) | → null, thêm `FLAG_NO_EMPLOYMENT` |
| `DAYS_BIRTH` | luôn âm | `AGE_YEARS = -DAYS_BIRTH / 365.25` |
| `CODE_GENDER` | 4 dòng `XNA` | → null, không gán giá trị thay thế |
| `ORGANIZATION_TYPE` | `XNA` ~18%, trùng nhóm nghỉ hưu | giữ thành hạng mục riêng, không coi là thiếu ngẫu nhiên |
| `AMT_INCOME_TOTAL` | outlier tại 117.000.000 | winsorize phân vị 99,9 hoặc log; **không xóa dòng** |
| `EXT_SOURCE_1` | thiếu ~56% | giữ null, thêm cờ thiếu |
| `OWN_CAR_AGE` | thiếu ~66% (vì không có xe) | giữ null, **không điền 0** |

Trong các bảng lịch sử, `XNA` và `XAP` cũng là giá trị thiếu, xử lý tương tự.

`DAYS_EMPLOYED` là rủi ro cao nhất: bỏ qua nó đưa giá trị tương đương 1.000 năm vào mọi phép trung bình.

### 3.7 Formatting và tooling

- `ruff format` + `ruff check` là nguồn chân lý duy nhất về format. Không tranh luận style thủ công.
- Dòng tối đa 100 ký tự.
- Import sắp theo stdlib / third-party / local, phân tách bằng dòng trống (ruff/isort lo).
- `from module import *` bị cấm.
- `mypy` ở mức strict cho package `src/`.
- Cấu hình tất cả trong `pyproject.toml`, không rải nhiều file config.

---

## 4. Kiến trúc

Dữ liệu chạy **một chiều** qua tám bước. Mỗi bước là một hàm nhận đường dẫn vào, ghi đường dẫn ra.

Nguyên tắc kiến trúc quan trọng nhất: **tách lớp tính toán khỏi lớp phục vụ.** DuckDB xử lý 58 triệu dòng và ghi Parquet; SQL Server chỉ chứa lớp mart nhỏ cho Power BI. **Không đưa dữ liệu thô vào SQL Server.**

### Tám bước

| # | Bước | Nội dung |
| --- | --- | --- |
| 1 | Ingest | đọc 8 CSV, ghi Parquet nén, không thay đổi nội dung |
| 2 | Contract check | đối chiếu số dòng, số cột, dtype, tính duy nhất PK |
| 3 | Normalize | xử lý 7 bẫy giá trị, đổi dấu `DAYS_*`, sinh cờ thiếu; một bảng silver mỗi bảng nguồn, giữ nguyên grain |
| 4 | **Holdout split** | rút 20% `SK_ID_CURR` phân tầng theo `TARGET`, ghi danh sách id ra file |
| 5 | Feature aggregation | gấp 6 bảng lịch sử về grain khách hàng bằng SQL trên DuckDB, qua hai tầng |
| 6 | Feature quality gate | rà cột hỏng và dấu hiệu rò rỉ trước huấn luyện |
| 7 | Train + calibrate | CV 5 fold, log MLflow, hiệu chỉnh xác suất, chọn ngưỡng theo chi phí |
| 8 | Load serving layer | dựng dimension + fact, nạp SQL Server qua bảng tạm, tạo FK, refresh Power BI |

**Ràng buộc thứ tự duy nhất không được đảo: bước 4 phải xong trước bước 5.** Tổng hợp đặc trưng trước khi chia dữ liệu là nguồn rò rỉ số một, biểu hiện là AUC CV cao hơn holdout 0,02–0,05.

### Cấu trúc thư mục

```
src/home_credit/
  config/          constants, YAML loaders, paths
  ingest/          step 1
  contracts/       step 2 Pandera schemas
  normalize/       step 3 silver layer
  split/           step 4 holdout
  features/        step 5 aggregation orchestration
  quality/         step 6 feature gates
  modeling/        step 7 training, calibration, thresholding
  serving/         step 8 star schema build + SQL Server load
  reporting/       metric extraction for README generation
sql/               DuckDB aggregation queries, SQL Server DDL
config/            feature_specs.yaml, pipeline.yaml
tests/             pytest, mirrors src layout
notebooks/         exploration and presentation only
data/              gitignored: raw/, bronze/, silver/, features/, models/
archive/           raw CSV source, gitignored
```

**Logic sản xuất nằm trong module Python import được.** Notebook chỉ dùng để khám phá và trình bày, không chứa logic pipeline. Nếu một đoạn code trong notebook cần chạy lại, nó thuộc về `src/`.

### Hai cấu trúc dữ liệu đầu ra

**A — ma trận huấn luyện:** một dòng một `SK_ID_CURR`, ~500–800 cột, rộng, phẳng, không chuẩn hóa, Parquet. Không index, không ràng buộc, **không nạp vào SQL Server**. Mỗi phiên bản đi kèm **manifest** ghi: danh sách cột, phép tổng hợp sinh ra từng cột, hash dữ liệu nguồn. Không manifest thì một cột như `BURO_AMT_CREDIT_SUM_MEAN` không truy được về cách tính.

**B — star schema BI:** hẹp, ~30 trường nghiệp vụ, tên cột đọc được, index và ràng buộc đầy đủ.

| Bảng | Grain | PK | Dòng dự kiến |
| --- | --- | --- | --- |
| `Fact_Application` | một đơn vay | `SK_ID_CURR` | 307.511 |
| `Dim_Occupation` | nghề nghiệp | `OccupationKey` | 19 |
| `Dim_Organization` | loại tổ chức | `OrgKey` | 59 |
| `Dim_Education` | trình độ | `EducationKey` | 6 |
| `Dim_ContractType` | loại hợp đồng | `ContractKey` | 3 |
| `Dim_HousingType` | hình thức cư trú | `HousingKey` | 7 |
| `Dim_FamilyStatus` | tình trạng hôn nhân | `FamilyKey` | 7 |
| `Dim_AgeBand` | nhóm tuổi | `AgeBandKey` | 7 |
| `Dim_IncomeBand` | nhóm thu nhập | `IncomeBandKey` | 6 |
| `Dim_RiskBand` | dải điểm rủi ro | `RiskBandKey` | 6 |

Số dòng dimension đã cộng một dòng cho giá trị không xác định.

`Fact_Application` mang ba nhóm cột: foreign key (9 cột `*Key`), measure (`AMT_CREDIT`, `AMT_ANNUITY`, `AMT_INCOME_TOTAL`, `AMT_GOODS_PRICE`, `CREDIT_INCOME_RATIO`, `ANNUITY_INCOME_RATIO`), và kết quả mô hình (`TARGET`, `PD_Predicted`, `CreditScore`, `Model_Version`, `IsHoldout`).

`TARGET` và `PD_Predicted` nằm cạnh nhau trong cùng fact là lựa chọn có chủ đích: cho phép dashboard đo chất lượng chính mô hình, không chỉ mô tả danh mục.

**Ba quy tắc dimension:**

1. Khóa là số nguyên tự sinh, **không dùng chuỗi nghiệp vụ làm khóa**.
2. Mỗi dimension có một dòng cho giá trị không xác định, khóa `-1`. Fact không bao giờ chứa FK null.
3. Dimension có thứ tự tự nhiên phải có cột `SortOrder`: `Dim_AgeBand`, `Dim_IncomeBand`, `Dim_RiskBand`, `Dim_Education`.

Mỗi `SK_ID_CURR` xuất hiện đúng một lần ⇒ không có slowly changing dimension.

---

## 5. Tech stack

Mỗi công nghệ giải quyết một ràng buộc cụ thể. Không thêm dependency không nêu được ràng buộc nó giải quyết.

| Lớp | Công nghệ | Ràng buộc |
| --- | --- | --- |
| Lưu trữ | Parquet | 58,4 triệu dòng CSV đọc chậm, chiếm nhiều dung lượng |
| Tổng hợp | DuckDB | `bureau_balance` 27,3 triệu dòng vượt RAM khi xử lý bằng DataFrame |
| Biến đổi bảng nhỏ | Polars (ưu tiên) hoặc pandas | `application_train` 307K dòng vừa bộ nhớ |
| Thuật toán | LightGBM | xử lý null native — bắt buộc vì `EXT_SOURCE_1` thiếu 56%, `OWN_CAR_AGE` thiếu 66% |
| Khung ML | scikit-learn | `Pipeline` và `ColumnTransformer` giữ mọi biến đổi trong fold |
| Hiệu chỉnh | `CalibratedClassifierCV` (isotonic) | class weight làm lệch xác suất đầu ra |
| Giải thích | SHAP `TreeExplainer` | cần giải thích ở mức tổng thể và từng hồ sơ |
| Theo dõi thực nghiệm | MLflow | số tổ hợp vượt khả năng ghi chép thủ công |
| Kiểm chất lượng | Pandera + pytest | quality gate chạy độc lập trong CI |
| Điều phối | Makefile, sau đó Prefect | chạy lại toàn pipeline bằng một lệnh |
| Kho phục vụ | SQL Server trên Docker | Power BI cần nguồn quan hệ có ràng buộc khóa |
| Báo cáo | Power BI | dashboard tương tác có tham số what-if |
| Môi trường | uv, pin phiên bản | tái tạo được trên máy khác |

### Công nghệ bị loại — không đề xuất lại

| Công nghệ | Lý do |
| --- | --- |
| Spark | 58 triệu dòng xử lý được trên một máy; thêm JVM mà không thêm năng lực |
| Airflow | chi phí vận hành vượt nhu cầu pipeline batch một người |
| SMOTE và biến thể | nội suy trên dữ liệu nhiều one-hot và nhiều null sinh mẫu không hợp lệ, phá hiệu chỉnh |
| Mạng nơ-ron | trên dữ liệu bảng quy mô này, gradient boosting tốt hơn với chi phí thấp hơn |

---

## 6. Feature engineering

Nhiệm vụ: gấp 58 triệu dòng về 307.511 dòng khách hàng mà không mất tín hiệu. **Toàn bộ viết bằng SQL trên DuckDB.**

### Tổng hợp hai tầng

1. `bureau_balance` → grain `SK_ID_BUREAU` → join `bureau` → grain `SK_ID_CURR`.
2. `POS_CASH_balance`, `installments_payments`, `credit_card_balance` → grain `SK_ID_PREV` → join `previous_application` → grain `SK_ID_CURR`.

Mọi phép nối là `LEFT JOIN` tính từ bảng cha.

### Bốn họ đặc trưng

| Họ | Cách tính | Số cột |
| --- | --- | --- |
| Tỷ lệ tại đơn hiện tại | phép chia giữa các trường trong application | 10–15 |
| Tổng hợp toàn lịch sử | count, sum, mean, max, min, std theo từng bảng | 250–350 |
| Tổng hợp theo cửa sổ | như trên, giới hạn 3, 6, 12, 24 tháng gần nhất | 150–250 |
| Xu hướng | `regr_slope` của số dư theo thời gian | 20–40 |

Sáu tỷ lệ bắt buộc có:
`AMT_CREDIT / AMT_INCOME_TOTAL`, `AMT_ANNUITY / AMT_INCOME_TOTAL`, `AMT_CREDIT / AMT_GOODS_PRICE`, `AMT_CREDIT / AMT_ANNUITY`, `DAYS_EMPLOYED / DAYS_BIRTH`, `AMT_INCOME_TOTAL / CNT_FAM_MEMBERS`.

**Họ cửa sổ thời gian là nơi tập trung giá trị cao nhất và thường bị bỏ qua.** Hành vi trả nợ 3 tháng gần nhất mang nhiều thông tin hơn hành vi 4 năm trước; tổng hợp toàn lịch sử làm loãng hai tín hiệu vào nhau.

### Hai đặc trưng trọng yếu từ `installments_payments`

- `DAYS_ENTRY_PAYMENT - DAYS_INSTALMENT` — số ngày trả muộn. Lấy mean, max, và tỷ lệ số lần dương.
- `AMT_PAYMENT / AMT_INSTALMENT` — tỷ lệ trả đủ. Dưới 1 là trả thiếu.

### Hai cấu hình đặc trưng song song

`EXT_SOURCE_1/2/3` là điểm do bên thứ ba tính sẵn — hợp lệ vì có mặt tại thời điểm xét duyệt, nhưng chiếm tỷ trọng rất lớn trong sức mạnh dự báo. Hệ thống huấn luyện **hai cấu hình**:

- `full` — có `EXT_SOURCE_*`, cho hiệu năng tốt nhất.
- `no_ext_source` — không có `EXT_SOURCE_*`, để đo sức mạnh tín hiệu nội bộ. **Chỉ cấu hình này dùng được cho phân tích nghiệp vụ.**

### Ba quy tắc kiểm soát số chiều

1. Danh sách cột × phép tổng hợp khai báo trong YAML. **Không vòng lặp quét toàn bộ.** `std` trên cờ nhị phân không mang thông tin.
2. Nhóm 47 cột mô tả căn hộ rút gọn **trước** khi tổng hợp. Ba biến thể `_AVG`, `_MODE`, `_MEDI` tương quan rất chặt; giữ một biến thể, hoặc thay toàn nhóm bằng một chỉ số tổng hợp cộng một cờ đầy đủ thông tin.
3. Lọc sau khi sinh, theo tiêu chí **cố định trước khi xem kết quả**: loại cột trên 95% null, cột một giá trị, và một trong hai cột có `|correlation| > 0,98`. Không điều chỉnh tiêu chí theo AUC.

---

## 7. Huấn luyện và chống rò rỉ

### Chia dữ liệu ba tầng

| Tầng | Tỷ lệ | Số đơn | Mục đích | Số lần truy cập |
| --- | --- | --- | --- | --- |
| Holdout | 20% | 61.502 | nghiệm thu cuối cùng | **đúng một lần** |
| Train qua CV | 80% | 246.009 | so sánh mô hình, dò siêu tham số | không giới hạn |
| Fold hiệu chỉnh | 1/5 fold | ~49.202 | hiệu chỉnh xác suất | mỗi lần huấn luyện |

Holdout tách ở bước 4, trước mọi phép tính đặc trưng, id ghi ra file để cố định qua các lần chạy.
**Holdout giữ được tính độc lập chỉ khi không được dùng để ra bất kỳ quyết định nào.**

### Cross-validation

Stratified K-fold, k = 5, phân tầng theo `TARGET`.

**Không dùng time-based validation.** `application_train` không có cột ngày nào, và `SK_ID_CURR` không đảm bảo tăng theo thời gian nộp đơn. Dùng id làm proxy cho trục thời gian là giả định không kiểm chứng được. Tài liệu kết quả phải nêu rõ lý do này.

### Năm nguồn rò rỉ và biện pháp chặn

Dữ liệu nguồn đã neo tại thời điểm nộp đơn (mọi `DAYS_*` và `MONTHS_BALANCE` đều âm). **Rò rỉ không đến từ dữ liệu mà từ quá trình xử lý.**

| Nguồn | Biểu hiện | Chặn |
| --- | --- | --- |
| Tổng hợp trước khi chia | AUC CV cao hơn holdout 0,02–0,05 | tách holdout ở bước 4, trước bước 5 |
| Target encoding ngoài fold | AUC CV rất cao, holdout sụt mạnh | tính encoding trong từng fold qua `Pipeline` |
| Điền thiếu bằng thống kê toàn tập | rò rỉ nhỏ nhưng có hệ thống | imputer trong `Pipeline`, fit trong fold |
| Chuẩn hóa trên toàn tập | rò rỉ nhỏ | fit chỉ trên phần train của fold |
| Cột trùng lặp / sao chép nhãn | hai cột `\|correlation\| = 1` | gate tương quan + gate AUC đơn biến ở bước 6 |

**Ràng buộc kỹ thuật tuyệt đối: mọi phép biến đổi phụ thuộc dữ liệu phải nằm trong `sklearn.pipeline.Pipeline`, không chạy rời trước vòng CV.** Áp cho imputer, scaler, encoder và mọi bước chọn đặc trưng.

### Hai kiểm định bắt buộc

1. **AUC đơn biến.** Với mỗi cột, tính `roc_auc_score(y, col)`. Cột vượt 0,95 phải điều tra trước khi huấn luyện. Chạy tự động ở gate bước 6. Tham chiếu: cả ba `EXT_SOURCE_*` cộng lại chỉ đạt ~0,70.
2. **Bỏ đặc trưng (leave-one-out).** Với 5 đặc trưng quan trọng nhất, huấn luyện lại mỗi lần loại một đặc trưng, ghi AUC vào bảng trong tài liệu. Mục đích: phát hiện trường hợp một đặc trưng đơn lẻ gánh phần lớn hiệu năng — dấu hiệu rò rỉ hoặc biến thay thế nhãn.

### Trình tự mô hình — bước 0 và 1 bắt buộc chạy và báo cáo

| # | Mô hình | Mục đích | AUC tham chiếu |
| --- | --- | --- | --- |
| 0 | dự đoán hằng số theo tỷ lệ cơ sở | mốc chặn dưới | 0,500 |
| 1 | logistic regression chỉ `EXT_SOURCE_*` | đo sức mạnh điểm bên thứ ba | ~0,70 |
| 2 | logistic regression với application + họ tỷ lệ | mốc cơ sở giải thích được | ~0,74 |
| 3 | LightGBM toàn bộ đặc trưng | mô hình chính | 0,78–0,79 |
| 4 | LightGBM không `EXT_SOURCE_*` | đo tín hiệu nội bộ | ~0,74 |

**Khoảng AUC hợp lý: 0,74 – 0,80. Giá trị vượt 0,85 là cảnh báo rò rỉ phải điều tra, không phải kết quả tốt.** Nếu một lần chạy cho AUC trên 0,85, dừng và báo cho người dùng trước khi tiếp tục.

---

## 8. Đánh giá

### Chỉ số

| Chỉ số | Dùng để | Ghi chú |
| --- | --- | --- |
| AUC ROC | so sánh mô hình, báo cáo chính | chỉ đo khả năng xếp hạng |
| PR-AUC | đánh giá trên lớp thiểu số | nhạy hơn AUC khi mất cân bằng |
| Brier score | đo độ chính xác xác suất | **bắt buộc sau hiệu chỉnh** |
| Reliability diagram | kiểm tra hiệu chỉnh trực quan | **bắt buộc đưa vào tài liệu** |
| Accuracy | **không dùng** | 91,93% đạt được bằng cách đoán tất cả 0 |

### Khoảng tin cậy

Holdout 20% (61.502 đơn, 4.964 ca dương) cho SE ≈ 0,0040 quanh AUC 0,78, CI 95% ≈ 0,772 – 0,788 theo Hanley–McNeil. Khoảng rộng ~0,016, đủ phân biệt hai mô hình chênh 0,01 AUC một cách có ý nghĩa.

**Mọi con số AUC trong tài liệu kết quả phải ghi kèm khoảng tin cậy.**

### Hiệu chỉnh xác suất

Quyết định cấp tín dụng cần xác suất đúng thang đo, không chỉ cần thứ tự xếp hạng. LightGBM + class weight cho xác suất lệch cao hơn thực tế ⇒ hiệu chỉnh là **bắt buộc**.

- Phương pháp: isotonic regression (phù hợp vì số mẫu lớn).
- Dữ liệu hiệu chỉnh: fold riêng, không dùng dữ liệu đã huấn luyện.
- Kiểm chứng: Brier score + reliability diagram.
- **AUC không đổi sau hiệu chỉnh vì thứ tự xếp hạng không đổi. Dùng AUC để kiểm tra hiệu chỉnh là sai.**

### Quy đổi điểm tín dụng

```
Score = Offset - Factor * ln(p / (1 - p))
```

Tham số chọn sao cho odds nhân đôi mỗi 20 điểm, neo tại 600. Chia năm dải A–E đổ vào `Dim_RiskBand`.

### Chỉ số nghiệp vụ

Ngưỡng quyết định chọn theo chi phí sai lầm, **không dùng 0,5**. Cấu trúc chi phí giả định — **phải nêu rõ là giả định trong mọi báo cáo**:

| Loại sai | Chi phí |
| --- | --- |
| Từ chối một khách không vỡ nợ | `AMT_CREDIT` × biên lợi nhuận |
| Duyệt một khách vỡ nợ | `AMT_CREDIT` × tỷ lệ tổn thất khi vỡ nợ |

Ba chỉ số báo cáo kèm theo:

1. Tỷ lệ duyệt tại ngưỡng đã chọn.
2. Tỷ lệ vỡ nợ trong nhóm được duyệt, so với 8,07% toàn bộ.
3. **Bảng decile** — tỷ lệ vỡ nợ thực tế theo từng decile điểm. Điều kiện chấp nhận: giảm đơn điệu từ decile rủi ro cao nhất xuống thấp nhất.

### Kiểm tra công bằng — bắt buộc, tính trên holdout

Dữ liệu chứa `CODE_GENDER` và `DAYS_BIRTH`; cho vay tiêu dùng chịu ràng buộc pháp lý về phân biệt theo giới và tuổi.

| Phép đo | Câu hỏi |
| --- | --- |
| Tỷ lệ duyệt theo nhóm | nhóm nào bị từ chối nhiều hơn tại cùng ngưỡng |
| AUC theo nhóm | mô hình chính xác đều giữa các nhóm không |
| **Độ hiệu chỉnh theo nhóm** | PD dự báo có khớp tỷ lệ vỡ nợ thực tế trong từng nhóm không |

Phép thứ ba quan trọng nhất: nếu mô hình ước lượng rủi ro một nhóm cao hơn thực tế, nhóm đó bị định giá bất lợi một cách có hệ thống dù rủi ro thực tương đương.

Phạm vi dừng ở **đo và báo cáo**. Khắc phục thiên lệch ngoài phạm vi, nhưng **kết quả đo phải được công bố kể cả khi bất lợi.**

---

## 9. Quality gate

Mỗi gate là một hàm trả về pass/fail, viết bằng Pandera hoặc pytest, **chạy được độc lập với pipeline**. **Gate không được nhúng vào hàm nạp dữ liệu.**

| Bước | Điều kiện | Khi fail |
| --- | --- | --- |
| 2 | số dòng và số cột khớp đặc tả | dừng |
| 2 | `SK_ID_CURR` duy nhất trong `application_train` | dừng |
| 2 | `SK_ID_BUREAU` duy nhất trong `bureau` | dừng |
| 3 | không còn giá trị `365243` trong bất kỳ cột `DAYS_*` | dừng |
| 3 | mọi `DAYS_*` ≤ 0 sau chuẩn hóa | dừng |
| 4 | giao giữa train và holdout là rỗng | dừng |
| 4 | tỷ lệ `TARGET` hai tập lệch < 0,1 điểm phần trăm | dừng |
| 5 | số dòng sau mọi join bằng số đơn vay | dừng |
| 6 | không cột nào toàn null hoặc chỉ một giá trị | loại cột, ghi log |
| 6 | không cột nào chứa giá trị vô cực | dừng |
| 6 | **không cột nào đạt AUC đơn biến > 0,95** | dừng và điều tra rò rỉ |
| 7 | AUC giữa các fold lệch < 0,02 | cảnh báo |
| 8 | mọi FK trong fact tồn tại trong dimension | dừng |
| 8 | số dòng fact bằng 307.511 | dừng |

Gate AUC đơn biến ở bước 6 là lớp phòng thủ quan trọng nhất. **Một cột đơn lẻ đạt AUC trên 0,95 trên bài toán rủi ro tín dụng gần như chắc chắn là rò rỉ, không phải phát hiện có giá trị.**

### Luật viết test

- Test mirror cấu trúc `src/`. `src/home_credit/normalize/applications.py` ↔ `tests/normalize/test_applications.py`.
- Một test một hành vi. Tên test mô tả hành vi, không mô tả hàm: `test_days_employed_sentinel_becomes_null`, không `test_normalize_1`.
- Test không chạm dữ liệu thật. Dùng fixture nhỏ dựng trong code, hoặc file fixture dưới 100 dòng trong `tests/fixtures/`.
- Test không cần internet, không cần SQL Server chạy. Test lớp serving dùng mock hoặc đánh dấu `@pytest.mark.integration`.
- Mọi bẫy giá trị ở §3.6 phải có test riêng.
- Mọi gate ở bảng trên phải có test cho cả nhánh pass và nhánh fail.

---

## 10. Lớp phục vụ và dashboard

### Nạp SQL Server

Mỗi lần chạy, pipeline ghi vào `stg_*` trước, sau đó đổi tên **trong một transaction duy nhất**. Bảng đích không bao giờ ở trạng thái dở dang khi Power BI đang đọc.

Ba ràng buộc:

1. **Độ dài cột chuỗi khai báo theo giá trị thực tế.** Không đặt `NVARCHAR(4000)` cho mọi cột — vượt giới hạn khóa 1700 byte và không index được.
2. **Tạo `PRIMARY KEY` và `FOREIGN KEY` thật sau khi đổi tên.** Ràng buộc ở tầng DB bắt được lỗi mà kiểm tra ở tầng ứng dụng bỏ sót.
3. **Một biến môi trường duy nhất cho cổng kết nối**, dùng chung cho `docker-compose`, script nạp và connection string Power BI. Lệch cổng giữa ba nơi là lỗi thường gặp và khó phát hiện.

### Bốn trang báo cáo

| Trang | Câu hỏi | Nội dung |
| --- | --- | --- |
| Danh mục | cơ cấu đơn vay | số đơn, giá trị, tỷ lệ vỡ nợ theo loại hợp đồng, nghề, trình độ |
| Yếu tố rủi ro | nhóm nào rủi ro hơn | tỷ lệ vỡ nợ theo nhóm tuổi, thu nhập, cư trú, hôn nhân |
| Chất lượng mô hình | mô hình tốt đến đâu | bảng decile, reliability diagram, AUC trên holdout |
| Ngưỡng quyết định | nên đặt ngưỡng ở đâu | tham số what-if, tỷ lệ duyệt và tổn thất dự kiến |

Trang Chất lượng mô hình **chỉ đọc dữ liệu có `IsHoldout = 1`** — phần duy nhất mô hình chưa từng thấy.

### Measure cần có

| Measure | Công thức | Định dạng |
| --- | --- | --- |
| Actual Default Rate | `DIVIDE(SUM(TARGET), COUNTROWS(Fact_Application))` | phần trăm |
| Average PD | `AVERAGE(PD_Predicted)` | phần trăm |
| Calibration Gap | `[Average PD] - [Actual Default Rate]` | điểm phần trăm |
| Approval Rate | `DIVIDE(COUNTROWS(FILTER(..., PD < Threshold)), COUNTROWS(...))` | phần trăm |
| Application Count | `COUNTROWS(Fact_Application)` | số nguyên |

**Calibration Gap là measure quan trọng nhất** của trang chất lượng mô hình. Cắt theo giới tính và nhóm tuổi, chính measure này thực hiện phép kiểm tra công bằng thứ ba.

### Bốn quy tắc mô hình ngữ nghĩa

1. **Mọi quan hệ một chiều**, từ fact sang dimension. Quan hệ hai chiều làm mẫu số của measure tỷ lệ bị lọc theo điều kiện tử số, cho ra 100%.
2. **Quan hệ tạo thủ công**, không dùng auto-detect.
3. **Ngưỡng trong DAX viết dạng phân số.** `DIVIDE` trả giá trị 0–1 ⇒ viết `> 0.07`, không viết `> 7`. Định dạng phần trăm đặt ở thuộc tính hiển thị.
4. **Tắt auto date/time.** Dữ liệu không có cột ngày nào; tính năng này chỉ sinh bảng ẩn vô ích.

Cột cờ và cột tỷ lệ (`TARGET`, `PD_Predicted`, `CREDIT_INCOME_RATIO`) đặt aggregation mặc định là **không tổng hợp**.

### Dữ liệu cá nhân

Bộ dữ liệu không chứa tên, số điện thoại hay địa chỉ. Định danh duy nhất là `SK_ID_CURR`, một số nguyên vô danh. **Không bổ sung tên giả cho mục đích trình bày** — điều đó tạo ấn tượng sai rằng báo cáo chứa hồ sơ khách hàng thật.

---

## 11. Git và môi trường

- `.gitignore` phải chặn: `archive/`, `data/`, `*.csv`, `*.parquet`, `mlruns/`, `*.pkl`, `*.joblib`, `.env`.
- Commit message tiếng Anh, thể mệnh lệnh, dòng đầu ≤ 72 ký tự: `Add bureau balance aggregation at loan grain`.
- Một commit một thay đổi logic. Không commit gộp "fix nhiều thứ".
- **Không commit hoặc push nếu người dùng không yêu cầu.**
- Nếu đang ở branch `main`, tạo branch trước khi commit.
- Phiên bản thư viện **pin** trong `pyproject.toml` + lockfile. Môi trường phải tái tạo được trên máy khác.
- Secret và connection string chỉ qua biến môi trường, đọc từ `.env` không commit. **Không hardcode port, password, server name.**

---

## 12. Tiêu chí nghiệm thu

Hệ thống hoàn thành khi thỏa 14 điều kiện. Mỗi điều kiện kiểm chứng được bằng cách chạy mã hoặc đọc tài liệu.

**Pipeline**

- [ ] Chạy lại toàn bộ từ dữ liệu thô trên máy sạch bằng **một lệnh duy nhất**
- [ ] Không bước nào ghi đè đầu vào của chính nó; chạy hai lần cho kết quả giống nhau
- [ ] Toàn bộ quality gate ở bước 2, 3, 4, 5, 6, 8 đều đạt
- [ ] Logic sản xuất nằm trong module Python import được, không nằm trong notebook
- [ ] Phiên bản thư viện được pin; môi trường tái tạo được trên máy khác

**Tính đúng đắn của mô hình**

- [ ] Holdout tách trước mọi phép tính đặc trưng, và chỉ được đọc một lần
- [ ] Kiểm định AUC đơn biến đã chạy; không cột nào vượt 0,95
- [ ] Kiểm định bỏ đặc trưng đã chạy cho 5 đặc trưng mạnh nhất, kết quả trong tài liệu
- [ ] Mọi biến đổi phụ thuộc dữ liệu nằm trong `Pipeline`, không chạy trước CV
- [ ] AUC holdout trong khoảng 0,74–0,80, hoặc có giải trình nếu vượt

**Kết quả báo cáo**

- [ ] Đã báo cáo mốc cơ sở: tỷ lệ nền và mô hình chỉ dùng `EXT_SOURCE_*`
- [ ] Xác suất đã hiệu chỉnh, có reliability diagram và Brier score
- [ ] Ngưỡng quyết định gắn với cấu trúc chi phí, kèm bảng decile
- [ ] Mọi con số AUC ghi kèm khoảng tin cậy
- [ ] Đã đo và công bố ba phép kiểm tra công bằng theo giới tính và nhóm tuổi

**Lớp phục vụ**

- [ ] Mọi quan hệ trong mô hình ngữ nghĩa là một chiều, mọi ngưỡng DAX dạng phân số
- [ ] Bốn trang báo cáo hoạt động, đọc trực tiếp từ SQL Server

**Tài liệu**

- [ ] Tài liệu kết quả nêu rõ ba giới hạn ở §1
- [ ] Phần số liệu trong tài liệu **sinh tự động** từ kết quả pipeline, không chép thủ công — một script đọc chỉ số từ MLflow và ghi vào tài liệu giữa hai dòng đánh dấu

---

## 13. Checklist trước khi báo cáo hoàn thành một thay đổi

1. `ruff format` và `ruff check` sạch.
2. `mypy src/` sạch.
3. `pytest` xanh; test mới đã viết cho hành vi mới.
4. Không có comment `#` nào trong file Python đã sửa (trừ shebang, `type: ignore`, `noqa`).
5. Không có chuỗi tiếng Việt nào trong code.
6. Không có magic number mới.
7. Nếu thêm cột đặc trưng: đã khai báo trong YAML và đã có trong manifest.
8. Nếu sửa logic pipeline: đã chạy lại bước đó và gate liên quan đạt.
9. Nếu AUC thay đổi: đã kiểm tra nó vẫn trong 0,74–0,80.
10. Báo cáo trung thực: test fail thì nói fail kèm output; bước nào bỏ qua thì nói rõ.
