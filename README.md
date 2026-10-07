# Home Credit Default Risk

Chấm điểm rủi ro vỡ nợ cho đơn vay tiêu dùng trên bộ dữ liệu Home Credit (8 bảng, ~58,4 triệu dòng).

## Tổng quan bài toán

Khách hàng của Home Credit thường có lịch sử tín dụng mỏng hoặc không có. Tại thời điểm xét duyệt cần biết khách có gặp khó khăn trả nợ ở các kỳ đầu hay không, và cân hai loại sai: từ chối khách tốt thì mất doanh thu, duyệt khách không trả được thì lỗ.

Hệ thống sinh ra:

1. Xác suất vỡ nợ đã hiệu chỉnh, kèm điểm tín dụng và dải xếp hạng A–E.
2. Ngưỡng quyết định chọn theo cấu trúc chi phí, không dùng 0,5.
3. Dashboard Power BI theo dõi chất lượng danh mục và chất lượng mô hình.

## Chạy

```bash
uv sync --extra dev
cp .env.example .env
make mssql-up      # SQL Server cho bước 8
make all           # bước 1-8
make evaluate      # mở holdout, chỉ chạy một lần
make readme        # ghi số liệu từ MLflow vào README
```

Tải dữ liệu từ [Kaggle](https://www.kaggle.com/c/home-credit-default-risk/data) vào `data/raw/`. `make help` liệt kê mọi target, `make check` chạy lint, mypy và test.

## Pipeline

| # | Bước | Lệnh | Gate |
| --- | --- | --- | --- |
| 1 | Ingest: CSV sang Parquet | `make ingest` | |
| 2 | Kiểm hợp đồng dữ liệu | `make contracts` | số dòng/cột, khóa chính duy nhất |
| 3 | Chuẩn hóa lớp silver | `make silver` | không còn `365243`, `DAYS_*` ≤ 0 |
| 4 | Tách holdout 20% | `make split` | train ∩ holdout rỗng, lệch `TARGET` < 0,1 điểm % |
| 5 | Tổng hợp đặc trưng (hai tầng) | `make features` | số dòng sau join = 307.511 |
| 6 | Kiểm đặc trưng và rò rỉ | `make gates` | không cột nào AUC đơn biến > 0,95 |
| 7 | Huấn luyện, hiệu chỉnh, chọn ngưỡng | `make train` | AUC giữa các fold lệch < 0,02 |
| 8 | Nạp SQL Server | `make serve` | FK đủ, fact = 307.511 dòng |

**Bước 4 phải xong trước bước 5.** Tổng hợp đặc trưng trước khi chia dữ liệu là nguồn rò rỉ số một.

Mô hình chạy theo trình tự: hằng số (AUC 0,50) → logistic chỉ `EXT_SOURCE_*` (~0,70) → logistic cơ sở (~0,74) → LightGBM đầy đủ (0,78–0,79) → LightGBM không `EXT_SOURCE_*` (~0,74). AUC trên 0,85 là cảnh báo rò rỉ.

## Tech stack

| Lớp | Công nghệ |
| --- | --- |
| Lưu trữ | Parquet |
| Tổng hợp 58 triệu dòng | DuckDB (SQL) |
| Biến đổi bảng nhỏ | Polars |
| Mô hình | LightGBM, scikit-learn `Pipeline` |
| Hiệu chỉnh | isotonic (`CalibratedClassifierCV`) |
| Giải thích | SHAP |
| Theo dõi thực nghiệm | MLflow |
| Kiểm chất lượng | Pandera, pytest |
| Điều phối | Makefile |
| Kho phục vụ | SQL Server (Docker) |
| Báo cáo | Power BI |
| Môi trường, lint | uv, ruff, mypy |

## Cấu trúc

```
configs/       YAML: hợp đồng dữ liệu, luật silver, đặc trưng, mô hình, chi phí
src/hcr/       logic sản xuất, chia theo tám bước
reports/       sinh số liệu cho README
powerbi/       bốn trang báo cáo, mô hình ngữ nghĩa TMDL
notebooks/     chỉ khám phá và trình bày
tests/         unit, gate, fixture nhỏ
```
