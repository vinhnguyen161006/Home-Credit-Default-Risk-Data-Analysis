## Đặc tả hệ thống — Home Credit Default Risk

O ct 7, 2026

Hệ thống chấm điểm rủi ro vỡ nợ cho đơn vay tiêu dùng, xây trên bộ dữ liệu Home Credit gồm 8 bảng quan hệ và khoảng 58,4 triệu dòng. Tài liệu này đặc tả dữ liệu nguồn, kiến trúc, quy trình xử lý, tiêu chí đánh giá và lộ trình triển khai.

·

@vinh

## Tổng quan

## Bài toán nghiệp vụ

Home Credit cấp tín dụng tiêu dùng cho nhóm khách hàng thường không đủ điều kiện vay ngân hàng truyền thống, nhiều người trong số đó có lịch sử tín dụng mỏng hoặc không có. Câu hỏi cần trả lời tại thời điểm xét duyệt: khách hàng này có khả năng gặp khó khăn trả nợ ở các kỳ đầu tiên không, và mức độ bao nhiêu.

Từ chuối sai cả hai phía đều có chi phí. Từ chối một khách tốt làm mất doanh thu và đẩy họ sang kênh vay không chính thức. Duyệt một khách không có khả năng trả gây lỗ cho bên cho vay và đẩy khách vào nợ xấu. Hệ thống này phục vụ việc cân hai chi phí đó một cách định lượng.

## Mục tiêu hệ thống

Hệ thống nhận hồ sơ đơn vay cùng toàn bộ lịch sử tín dụng liên quan, và sinh ra ba thứ:

- 1. Xác suất vỡ nợ đã hiệu chỉnh cho từng đơn, kèm điểm tín dụng quy đổi và dải xếp hạng.

- 2. Một ngưỡng quyết định gắn với cấu trúc chi phí, kèm tỷ lệ duyệt và tổn thất dự kiến tương ứng.

- 3. Lớp báo cáo cho phép theo dõi chất lượng danh mục và chất lượng chính mô hình.

## Đầu ra bàn giao

| Sản phẩm Dạng Điều kiện chấp nhận Pipeline dữ liệu mã nguồn Python có thể chạy lại toàn bộ từ CSV thô bằng một import lệnh Ma trận đặc trưng Parquet có phiên bản kèm manifest ghi cột và phép tổng hợp Mô hình chấm artifact đã hiệu chỉnh có reliability diagram và Brier score điểm |
| --- |


| Sản phẩm | Dạng | Điều kiện chấp nhận |
| --- | --- | --- |
| Lớp dữ liệu BI | bảng trong SQL Server | ràng buộc khóa chính và khóa ngoại |
|   |   | đầy đủ |
| Dashboard | báo cáo Power BI | bốn trang, nối trực tiếp vào SQL Server |
| Tài liệu kết quả | README | số liệu sinh tự động từ kết quả pipeline |

## Phạm vi

Trong phạm vi: xử lý dữ liệu theo lô, sinh đặc trưng, huấn luyện và hiệu chỉnh mô hình, chọn ngưỡng theo chi phí, kiểm tra công bằng, mô hình dữ liệu BI và dashboard.

Ngoài phạm vi: chấm điểm thời gian thực qua API, giám sát trôi dạt mô hình trong vận hành, hệ thống ra quyết định tự động, và tích hợp với hệ thống cấp tín dụng thật.

## Ba giới hạn phải chấp nhận

Ba điều sau là thuộc tính của dữ liệu, không khắc phục được bằng kỹ thuật, và chúng ràng buộc những gì hệ thống có thể hứa:

- Không có ngày tháng tuyệt đối. Mọi mốc thời gian là số ngày hoặc số tháng tương đối so với ngày nộp đơn. Hệ quả: không dựng được bảng chiều ngày thực, không có phân tích xu hướng theo tháng dương lịch, và không kiểm định được mô hình theo trục thời gian.

- Ngưỡng chính xác của nhãn không được công bố. Xem mục biến mục tiêu. Hệ quả: xác suất đầu ra không dịch trực tiếp sang PD theo chuẩn Basel.

- Tập application_test.csv không có nhãn. Mọi đo lường phải dựa trên tập holdout tách ra từ application_train.csv .

## Mô tả dữ liệu nguồn

Tám tệp CSV, tổng khoảng 58,4 triệu dòng. Bảng trung tâm application_train chỉ chiếm 0,5% khối lượng; 99,5% số dòng nằm ở bốn bảng lịch sử theo tháng. Đặc điểm này chi phối mọi quyết định về công nghệ và kiến trúc ở các mục sau.

| Tệp |   | Dòng Cột Grain (một | Khóa |
| --- | --- | --- | --- |
|   |   | dòng = ) |   |
| application_train.csv | 307.511 | 122 một đơn vay | SK_ID_CURR (PK) |
|   |   | đang xét duyệt |   |


| Tệp | Dòng Cột Grain (một |   | Khóa |
| --- | --- | --- | --- |
|   |   | dòng = ) |   |
| application_test.csv | 48.744 | 121 như trên, | SK_ID_CURR (PK) |
|   |   | không có cột |   |
|   |   | TARGET |   |
| bureau.csv | 1.716.428 | 17 một khoản vay | SK_ID_BUREAU |
|   |   | tại tổ chức tín | (PK), SK_ID_CURR |
|   |   | dụng khác | (FK) |
| bureau_balance.csv | 27.299.925 | 3 một khoản vay | SK_ID_BUREAU (FK) |
|   |   | bên ngoài × |   |
|   |   | một tháng |   |
| previous_application.csv | 1.670.214 | 37 một đơn vay | SK_ID_PREV (PK), |
|   |   | trước tại Home | SK_ID_CURR (FK) |
|   |   | Credit |   |
| POS_CASH_balance.csv | 10.001.358 | 8 một hợp đồng | SK_ID_PREV (FK) |
|   |   | POS hoặc cash |   |
|   |   | × một tháng |   |
| installments_payments.csv | 13.605.401 | 8 một lần trả góp | SK_ID_PREV (FK) |
|   |   | đã thực hiện |   |
| credit_card_balance.csv | 3.840.312 | 23 một thẻ tín | SK_ID_PREV (FK) |
|   |   | dụng × một |   |
|   |   | tháng |   |

Số dòng và cột của bureau và bureau_balance được đối chiếu với phân tích của Ashok Harnal. Bộ dữ liệu gốc ở Kaggle. [URL 🔗](https://harnalashok.github.io/credit_risk/bureau.html)

## Nhóm trường trong bảng trung tâm

122 cột của application_train chia thành năm nhóm:

| Nhóm Số cột xấp Ví dụ trường xỉ Thông tin khoản vay 8 AMT_CREDIT , AMT_ANNUITY , AMT_GOODS_PRICE , NAME_CONTRACT_TYPE Nhân khẩu và nghề 20 DAYS_BIRTH , CODE_GENDER , OCCUPATION_TYPE , nghiệp ORGANIZATION_TYPE |
| --- |


| Nhóm | Số cột xấp | Ví dụ trường |
| --- | --- | --- |
|   | xỉ |   |
| Tài chính và tài sản | 12 | AMT_INCOME_TOTAL , FLAG_OWN_CAR , |
|   |   | OWN_CAR_AGE , NAME_HOUSING_TYPE |
| Điểm tín dụng ngoài | 3 | EXT_SOURCE_1 , EXT_SOURCE_2 , EXT_SOURCE_3 |
| Thuộc tính nơi ở và cờ hồ | 79 | APARTMENTS_AVG , FLAG_DOCUMENT_* , |
| sơ |   | AMT_REQ_CREDIT_BUREAU_* |

Nhóm cuối chiếm gần hai phần ba số cột nhưng đóng góp ít nhất về sức mạnh dự báo. Trong đó, 47 cột mô tả đặc điểm căn hộ (diện tích, số tầng, vật liệu) có tỷ lệ thiếu rất cao và tương quan chặt với nhau theo ba biến thể _AVG , _MODE , _MEDI . Đặc tả xử lý nhóm này nằm ở mục feature engineering.

## Sơ đồ quan hệ

Không bảng lịch sử nào nối trực tiếp về application_train . Bốn bảng lớn nhất đều nằm ở tầng ba và chỉ nối được qua SK_ID_BUREAU hoặc SK_ID_PREV . Vì vậy mọi đặc trưng từ tầng ba phải tổng hợp hai lần: trước hết về grain của tầng hai, sau đó về grain khách hàng.

quan hệ ba tầng · 7 bảng, 3 khóa

Hai điểm cần lưu ý khi hiện thực:


- Mọi quan hệ đều là một–nhiều theo chiều mũi tên. Một khách có thể có nhiều khoản vay bên ngoài, mỗi khoản có nhiều dòng lịch sử tháng.

- installments_payments không phải bảng theo tháng mà là bảng sự kiện: mỗi dòng là một lần trả thực tế. Đây là khác biệt quan trọng vì nó cho phép tính độ trễ trả nợ ở mức từng giao dịch.

## Biến mục tiêu

## Định nghĩa

TARGET là biến nhị phân trong application_train . Giá trị 1 nghĩa là khách hàng gặp khó khăn trả nợ: chậm thanh toán quá X ngày ở ít nhất một trong Y kỳ trả đầu tiên của khoản vay. Giá trị 0 là mọi trường hợp còn lại.

Hai tính chất của định nghĩa này có hệ quả trực tiếp đến thiết kế:

Nhãn neo ở cửa số cố định. Vì chỉ xét Y kỳ đầu, mọi đơn vay được quan sát trong cùng một độ dài thời gian kể từ khi giải ngân. Nhờ vậy nhãn không phụ thuộc vào việc khoản vay đã tất toán hay chưa, và không cần loại trừ khoản vay đang chạy.

X và Y không được công bố. Không biết nhãn tương ứng với chậm 30, 60 hay 90 ngày, cũng không biết cửa sổ là 3 hay 6 kỳ. Hệ quả: xác suất mô hình sinh ra là xác suất của sự kiện này, không phải PD theo định nghĩa Basel, và không quy đổi trực tiếp sang tổn thất thực. Tài liệu kết quả phải nói rõ điều này.

## Phân bố lớp

| Lớp | Số đơn | Tỷ lệ |
| --- | --- | --- |
| TARGET = 0 |   | 282.686 91,93% |
| TARGET = 1 | 24.825 | 8,07% |
| Tổng | 307.511 | 100% |

Tỷ lệ xấp xỉ 11,4 ca âm trên mỗi ca dương. Mức mất cân bằng này có ba hệ quả bắt buộc:

- 1. Accuracy bị cấm dùng làm chỉ số đánh giá. Dự đoán tất cả bằng 0 đạt accuracy 91,93% mà không phát hiện được ca vỡ nợ nào.

- 2. Không dùng ngưỡng mặc định 0,5. Ngưỡng phải chọn theo chi phí sai lầm, xem mục đặc tả đánh giá.

- 3. Không dùng kỹ thuật sinh mẫu tổng hợp. Tỷ lệ 11,4:1 nằm trong tầm xử lý của trọng số lớp. Sinh mẫu nhân tạo làm sai lệch xác suất đầu ra, phá đúng thứ hệ thống cần.


## Chất lượng dữ liệu

## Bẫy giá trị đã biết

Bảy trường sau chứa giá trị không thể dùng trực tiếp. Xử lý ở lớp silver là bắt buộc, không phải tùy chọn.

| Trường | Vấn đề | Xử lý bắt buộc |
| --- | --- | --- |
| DAYS_EMPLOYED | giá trị 365243 là mã quy ước | chuyển thành null, thêm cờ |
|   | cho người không đi làm, chiếm | FLAG_NO_EMPLOYMENT |
|   | khoảng 18% số dòng |   |
| DAYS_BIRTH | luôn mang giá trị âm | AGE_YEARS = -DAYS_BIRTH / |
|   |   | 365.25 |
| CODE_GENDER | 4 dòng mang giá trị XNA | chuyển thành null, không gán giá trị |
|   |   | thay thế |
| ORGANIZATION_TYPE | XNA khoảng 18%, trùng gần | giữ thành hạng mục riêng, không |
|   | hết với nhóm nghỉ hưu | coi là thiếu ngẫu nhiên |
| AMT_INCOME_TOTAL | có giá trị cực đoan tại | winsorize ở phân vị 99,9 hoặc lấy |
|   | 117.000.000 | logarit; không xóa dòng |
| EXT_SOURCE_1 | thiếu khoảng 56% | giữ null, thêm cờ thiếu |
| OWN_CAR_AGE | thiếu khoảng 66% | thiếu vì không sở hữu xe; giữ null, |
|   |   | không điền 0 |

Trường DAYS_EMPLOYED là rủi ro cao nhất trong nhóm này. Bỏ qua nó làm sai toàn bộ thống kê về thâm niên công tác, và đưa một giá trị tương đương 1.000 năm vào mọi phép tính trung bình.

Trong các bảng lịch sử, hai mã XNA và XAP cũng đóng vai trò giá trị thiếu và cần xử lý tương tự.

## Khoảng trống phủ dữ liệu

Hai khoảng trống sau quyết định cách viết phép join và cách xử lý null ở lớp đặc trưng.


| Khoảng trống | Số liệu | Hệ quả thiết kế |
| --- | --- | --- |
| Khoản vay bên ngoài | 817.395 trên 1.716.428 dòng | dùng LEFT JOIN ; INNER JOIN sẽ |
| không có lịch sử | bureau có dữ liệu trong | làm mất hơn nửa lịch sử |
| tháng | bureau_balance , tức khoảng |   |
|   | 48% |   |
| Khách không có lịch | bureau phủ 305.811 trên | giữ null, thêm cờ |
| sử tín dụng bên | 307.511 khách; khoảng 1.700 | FLAG_NO_BUREAU_HISTORY |
| ngoài | khách không có bản ghi nào |   |

Nguyên tắc chung áp cho toàn hệ thống: thiếu dữ liệu không phải giá trị không. Một khách có BURO_AMT_CREDIT_SUM_MEAN bằng 0 nghĩa là đã từng vay với số tiền 0 đồng, khác hẳn khách chưa từng vay ở đâu. Điền 0 xóa mất phân biệt giữa khách hồ sơ mỏng và khách có lịch sử sạch — đúng nhóm mà bài toán này cần phân biệt nhất.

## Kiến trúc hệ thống

Dữ liệu chạy một chiều qua tám bước. Mỗi bước là một hàm nhận đường dẫn vào và ghi ra đường dẫn mới; không bước nào được ghi đè đầu vào của chính nó, nhờ vậy chạy lại nhiều lần luôn cho cùng kết quả.


## Dir liéu chay mgt chiéu qua tam buéc, tir CSV dén dashboard

kiến trúc lớp · 8 bước, một chiều

Nguyên tắc kiến trúc quan trọng nhất là tách lớp tính toán khỏi lớp phục vụ. DuckDB xử lý khối 58 triệu dòng và ghi kết quả ra Parquet; SQL Server chỉ chứa lớp mart nhỏ để Power BI truy vấn. Đưa dữ liệu thô vào SQL Server làm chậm cả hai phía mà không mang lại lợi ích nào.

Lớp tô màu là ràng buộc thứ tự duy nhất không được phép đảo: holdout phải tách xong trước khi bất kỳ phép tổng hợp nào chạy. Lý do và cơ chế nằm ở mục đặc tả huấn luyện.

## Mô hình dữ liệu đầu ra

Hệ thống sinh ra hai cấu trúc dữ liệu khác hình dạng, không dùng chung một bảng. Chúng phục vụ hai loại truy cập khác nhau và không thể tối ưu đồng thời.


## Cấu trúc A — ma trận huấn luyện

Một dòng một SK_ID_CURR , khoảng 500–800 cột sau tổng hợp. Rộng, phẳng, không chuẩn hóa, lưu dạng Parquet. Truy cập duy nhất là đọc toàn bộ vào bộ nhớ để huấn luyện, nên không cần index, không cần ràng buộc, và không nạp vào SQL Server.

Mỗi phiên bản ma trận phải đi kèm một tệp manifest ghi ba thứ: danh sách cột, phép tổng hợp sinh ra từng cột, và mã băm của dữ liệu nguồn. Không có manifest thì một cột tên BURO_AMT_CREDIT_SUM_MEAN không truy được về cách tính.

## Cấu trúc B — star schema cho báo cáo

Hẹp, nhỏ, tên cột đọc được, khoảng 30 trường nghiệp vụ. Truy cập là truy vấn tổng hợp từ Power BI, nên cần index và ràng buộc đầy đủ.

| Bảng | Grain | Khóa chính | Số dòng dự kiến |
| --- | --- | --- | --- |
| Fact_Application | một đơn vay | SK_ID_CURR | 307.511 |
| Dim_Occupation | nghề nghiệp | OccupationKey | 19 |
| Dim_Organization | loại tổ chức làm việc | OrgKey | 59 |
| Dim_Education | trình độ học vấn | EducationKey | 6 |
| Dim_ContractType | loại hợp đồng vay | ContractKey | 3 |
| Dim_HousingType | hình thức cư trú | HousingKey | 7 |
| Dim_FamilyStatus | tình trạng hôn nhân | FamilyKey | 7 |
| Dim_AgeBand | nhóm tuổi | AgeBandKey | 7 |
| Dim_IncomeBand | nhóm thu nhập | IncomeBandKey | 6 |
| Dim_RiskBand | dải điểm rủi ro | RiskBandKey | 6 |

Số dòng dimension đã cộng thêm một dòng cho giá trị không xác định.

## Cột của bảng fact

Fact_Application mang ba nhóm cột:

| Nhóm | Cột |
| --- | --- |
| Khóa ngoại | OccupationKey , OrgKey , EducationKey , |
|   | ContractKey , HousingKey , FamilyKey , |
|   | AgeBandKey , IncomeBandKey , RiskBandKey |


| Nhóm | Cột |
| --- | --- |
| Số đo | AMT_CREDIT , AMT_ANNUITY , AMT_INCOME_TOTAL , |
|   | AMT_GOODS_PRICE , CREDIT_INCOME_RATIO , |
|   | ANNUITY_INCOME_RATIO |
| Kết quả mô hình | TARGET , PD_Predicted , CreditScore , |
|   | Model_Version , IsHoldout |

Cột TARGET và PD_Predicted nằm cạnh nhau trong cùng bảng fact là lựa chọn có chủ đích: nó cho phép dashboard đo chất lượng chính mô hình, không chỉ mô tả danh mục. Cờ IsHoldout cho phép tách riêng phần chưa bao giờ được huấn luyện khi đọc chỉ số.

## Ba quy tắc bắt buộc cho dimension

- 1. Khóa là số nguyên tự sinh, không dùng chuỗi nghiệp vụ làm khóa. Chuỗi dài không index được hiệu quả và dễ vỡ vì khác biệt khoảng trắng hoặc chữ hoa.

- 2. Mỗi dimension có một dòng cho giá trị không xác định, khóa -1 . Nhờ vậy bảng fact không bao giờ chứa khóa ngoại null, và báo cáo không sinh dòng trống.

- 3. Dimension có thứ tự tự nhiên phải có cột SortOrder . Áp dụng cho Dim_AgeBand , nhóm theo bảng chữ cái. Dim_IncomeBand , Dim_RiskBand và Dim_Education . Thiếu cột này, biểu đồ sẽ sắp

Mỗi SK_ID_CURR xuất hiện đúng một lần trong application_train , nên không phát sinh bài toán chiều biến đổi chậm. Mọi thuộc tính đều là thuộc tính tại thời điểm nộp đơn và nằm trực tiếp trong bảng fact.

## Tech stack

Tiêu chí chọn: mỗi công nghệ phải giải quyết một ràng buộc cụ thể của bộ dữ liệu này. Cột cuối nêu ràng buộc đó.

| Lớp | Công nghệ | Ràng buộc nó giải quyết |
| --- | --- | --- |
| Định dạng lưu | Parquet | 58,4 triệu dòng CSV đọc chậm và chiếm |
| trữ |   | quá nhiều dung lượng |
| Tính toán tổng | DuckDB | bureau_balance 27,3 triệu dòng vượt bộ |
| hợp |   | nhớ khả dụng khi xử lý bằng DataFrame |
| Biến đổi bảng | Polars hoặc pandas | application_train 307K dòng vừa bộ |
| nhỏ |   | nhớ, thao tác cột linh hoạt hơn |


| Lớp | Công nghệ | Ràng buộc nó giải quyết |
| --- | --- | --- |
| Thuật toán | LightGBM | xử lý null native, cần thiết vì |
|   |   | EXT_SOURCE_1 thiếu 56% và |
|   |   | OWN_CAR_AGE thiếu 66% |
| Khung pipeline | scikit-learn | Pipeline và ColumnTransformer giữ |
| ML |   | mọi phép biến đổi nằm trong fold |
| Hiệu chỉnh xác | CalibratedClassifierCV | trọng số lớp làm lệch xác suất đầu ra |
| suất |   |   |
| Giải thích mô | SHAP TreeExplainer | cần giải thích ở cả mức tổng thể lẫn từng |
| hình |   | hồ sơ |
| Theo dõi thực | MLflow | số lượng tổ hợp đặc trưng và siêu tham |
| nghiệm |   | số vượt khả năng ghi chép thủ công |
| Kiểm chất lượng Pandera và pytest |   | quality gate phải chạy được độc lập trong |
|   |   | CI |
| Điều phối | Makefile, sau đó Prefect | yêu cầu chạy lại toàn pipeline bằng một |
|   |   | lệnh |
| Kho phục vụ | SQL Server trên Docker | Power BI cần nguồn quan hệ có ràng |
|   |   | buộc khóa |
| Báo cáo | Power BI | yêu cầu dashboard tương tác có tham số |
|   |   | what-if |
| Môi trường | uv hoặc conda, pin phiên | kết quả phải tái tạo được trên máy khác |
|   | bản |   |

## Ghi chú về ba lựa chọn

DuckDB ở lớp tổng hợp. bureau_balance có 27,3 triệu dòng × 3 cột. Đọc bằng pandas với kiểu suy mặc định int64 chiếm nhiều GB trước khi tính toán bắt đầu, và phép groupby nhân thêm bộ nhớ trung gian. DuckDB đọc Parquet theo cột và xử lý ngoài bộ nhớ khi cần, nên không phụ thuộc RAM. Viết bằng SQL thuần cũng dễ rà soát hơn chuỗi

groupby().agg() lồng nhau.

LightGBM thay vì hồi quy logistic làm mô hình chính. Lý do kỹ thuật cụ thể: dữ liệu có tỷ lệ thiếu rất cao ở nhiều cột quan trọng, và bản thân việc thiếu là tín hiệu (khách không có xe, khách không có lịch sử tín dụng). Cây quyết định học được hướng rẽ của nhánh thiếu; hồi quy logistic buộc phải điền giá trị và làm mất tín hiệu đó.


SQL Server chỉ ở lớp phục vụ. Kho phục vụ chứa khoảng 307 nghìn dòng fact và vài trăm dòng dimension — nhỏ hơn dữ liệu thô khoảng 190 lần. Thiết lập một biến môi trường duy nhất cho cổng kết nối và dùng chung cho cả docker-compose , script nạp và chuỗi kết nối

của Power BI.

## Công nghệ không dùng

| Công nghệ | Lý do loại |
| --- | --- |
| Spark | 58 triệu dòng nằm trong tầm xử lý một máy; thêm |
|   | JVM và cấu hình mà không thêm năng lực |
| Airflow | chi phí vận hành vượt nhu cầu của pipeline batch |
|   | một người |
| SMOTE và biến thể nội suy trên dữ liệu nhiều cột one-hot và nhiều null |   |
|   | sinh mẫu không hợp lệ, và phá hiệu chỉnh xác suất |
| Mạng nơ-ron | trên dữ liệu bảng quy mô này, gradient boosting |
|   | cho kết quả tốt hơn với chi phí thấp hơn |

## Đặc tả pipeline

## Các bước xử lý

Mỗi bước là một hàm Python có thể import và kiểm thử độc lập. Notebook chỉ dùng để khám phá và trình bày, không chứa logic sản xuất.

- 1. Ingest — đọc 8 tệp CSV, ghi ra Parquet có nén, không thay đổi nội dung.

- 2. Kiểm hợp đồng — đối chiếu số dòng, số cột, kiểu dữ liệu và tính duy nhất khóa chính với đặc tả ở mục mô tả dữ liệu nguồn.

- 3. Chuẩn hóa — xử lý bảy bẫy giá trị, đổi dấu các trường DAYS_* , sinh cờ thiếu. Một bảng silver cho mỗi bảng nguồn, giữ nguyên grain.

- 4. Tách holdout — rút 20% SK_ID_CURR theo phân tầng trên TARGET, ghi danh sách id ra tệp. Bước này bắt buộc đứng trước bước 5.

- 5. Tổng hợp đặc trưng — gấp 6 bảng lịch sử về grain khách hàng bằng SQL trên DuckDB, qua hai tầng tổng hợp.

- 6. Kiểm chất lượng đặc trưng — rà cột hỏng và dấu hiệu rò rỉ trước khi huấn luyện.

- 7. Huấn luyện và hiệu chỉnh — CV 5 fold, ghi thực nghiệm vào MLflow, hiệu chỉnh xác suất, chọn ngưỡng theo chi phí.


- 8. Nạp lớp phục vụ — dựng dimension và fact, nạp vào SQL Server qua bảng tạm, tạo ràng buộc khóa, refresh Power BI.

## Quality gate

Mỗi gate là một hàm trả về đạt hoặc không đạt, viết bằng Pandera hoặc pytest, chạy được độc lập với pipeline. Gate không được nhúng vào hàm nạp dữ liệu.

| Bước Điều kiện kiểm tra |   | Hành động khi không đạt |
| --- | --- | --- |
| 2 | số dòng và số cột khớp đặc tả | dừng |
| 2 | SK_ID_CURR duy nhất trong application_train | dừng |
| 2 | SK_ID_BUREAU duy nhất trong bureau | dừng |
| 3 | không còn giá trị 365243 trong bất kỳ cột DAYS_* | dừng |
| 3 | mọi DAYS_* nhỏ hơn hoặc bằng 0 sau chuẩn hóa | dừng |
| 4 | giao giữa tập huấn luyện và holdout là rỗng | dừng |
| 4 | tỷ lệ TARGET hai tập lệch dưới 0,1 điểm phần trăm dừng |   |
| 5 | số dòng sau mọi join bằng số đơn vay | dừng |
| 6 | không cột nào toàn null hoặc chỉ một giá trị | loại cột, ghi log |
| 6 | không cột nào chứa giá trị vô cực | dừng |
| 6 | không cột nào đạt AUC đơn biến trên 0,95 | dừng và điều tra rò rỉ |
| 7 | AUC giữa các fold lệch dưới 0,02 | cảnh báo |
| 8 | mọi khóa ngoại trong fact tồn tại trong dimension dừng |   |
| 8 | số dòng fact bằng 307.511 | dừng |

Gate tại bước 6 về AUC đơn biến là lớp phòng thủ quan trọng nhất. Nguyên tắc: một cột đơn lẻ đạt AUC trên 0,95 trên bài toán rủi ro tín dụng gần như chắc chắn là dấu hiệu rò rỉ hoặc trùng lặp với nhãn, không phải phát hiện có giá trị. Để tham chiếu, cả ba cột EXT_SOURCE_* cộng lại chỉ đạt khoảng 0,70.

## Đặc tả feature engineering

Nhiệm vụ: gấp 58 triệu dòng lịch sử về 307.511 dòng khách hàng mà không mất tín hiệu. Toàn bộ viết bằng SQL trên DuckDB.


## Tổng hợp hai tầng

Bốn bảng lớn nhất nằm ở tầng ba nên phải gấp hai lần:

- 1. bureau_balance gấp về grain SK_ID_BUREAU , sau đó nối vào bureau và gấp tiếp về SK_ID_CURR .

- 2. POS_CASH_balance , installments_payments , credit_card_balance gấp về grain SK_ID_PREV , sau đó nối vào previous_application và gấp tiếp về SK_ID_CURR .

Mọi phép nối dùng LEFT JOIN tính từ bảng cha, vì tỷ lệ phủ không đầy đủ như đã nêu ở mục chất lượng dữ liệu.

## Bốn họ đặc trưng

| Họ | Cách tính | Số cột ước |
| --- | --- | --- |
|   |   | tính |
| Tỷ lệ tại đơn vay hiện tại | phép chia giữa các trường trong | 10–15 |
|   | application |   |
| Tổng hợp toàn lịch sử | count, sum, mean, max, min, std theo từng | 250–350 |
|   | bảng |   |
| Tổng hợp theo cửa sổ thời | như trên nhưng giới hạn 3, 6, 12, 24 tháng gần | 150–250 |
| gian | nhất |   |
| Xu hướng | regr_slope của số dư theo thời gian | 20–40 |

Họ tỷ lệ rẻ nhất và thường nằm trong nhóm đặc trưng mạnh nhất. Sáu tỷ lệ cần có:

AMT_CREDIT / AMT_INCOME_TOTAL , AMT_ANNUITY / AMT_INCOME_TOTAL , AMT_CREDIT / AMT_GOODS_PRICE , AMT_CREDIT / AMT_ANNUITY , DAYS_EMPLOYED / DAYS_BIRTH , và AMT_INCOME_TOTAL / CNT_FAM_MEMBERS .

Họ cửa sổ thời gian là nơi tập trung giá trị cao nhất và thường bị bỏ qua. Hành vi trả nợ ba tháng gần nhất mang nhiều thông tin hơn hành vi bốn năm trước, nhưng phép tổng hợp toàn lịch sử làm loãng hai tín hiệu đó vào nhau.

## Hai đặc trưng trọng yếu

Từ installments_payments , hai đại lượng sau đo trực tiếp hành vi trả nợ, không qua biến trung gian:

- DAYS_ENTRY_PAYMENT - DAYS_INSTALMENT — số ngày trả muộn so với hạn. Lấy mean, max, và tỷ lệ số lần dương.

- AMT_PAYMENT / AMT_INSTALMENT — tỷ lệ trả đủ. Giá trị dưới 1 là trả thiếu.


## Về ba cột điểm tín dụng ngoài

EXT_SOURCE_1 , EXT_SOURCE_2 , EXT_SOURCE_3 là điểm do bên thứ ba tính sẵn. Chúng hợp

lệ vì có mặt tại thời điểm xét duyệt, nhưng chiếm tỷ trọng rất lớn trong sức mạnh dự báo.

Hệ thống vì vậy huấn luyện hai cấu hình đặc trưng song song: cấu hình đầy đủ cho hiệu năng tốt nhất, và cấu hình không có EXT_SOURCE_* để đo sức mạnh của tín hiệu nội bộ. Cấu hình thứ hai mới dùng được cho phân tích nghiệp vụ, vì nó chỉ ra yếu tố nào trong hồ sơ khách hàng thực sự liên quan đến rủi ro.

## Kiểm soát số chiều

Làm đầy đủ bốn họ trên cho 6 bảng sinh ra hàng nghìn cột. Ba quy tắc giới hạn:

- 1. Danh sách cột × phép tổng hợp khai báo trong tệp cấu hình YAML, không dùng vòng lặp quét toàn bộ. Phép std trên một cờ nhị phân không mang thông tin.

- 2. Nhóm 47 cột mô tả căn hộ rút gọn trước khi tổng hợp. Ba biến thể _AVG , _MODE , _MEDI của cùng một thuộc tính tương quan rất chặt; giữ một biến thể, hoặc thay toàn nhóm bằng một chỉ số tổng hợp cộng một cờ đầy đủ thông tin.

- 3. Lọc sau khi sinh, theo tiêu chí cố định trước. Loại cột trên 95% null, cột chỉ một giá trị, và một trong hai cột có tương quan tuyệt đối trên 0,98. Tiêu chí phải cố định trước khi xem kết quả, không điều chỉnh theo AUC.

## Quy tắc xử lý giá trị thiếu

Sau LEFT JOIN , khách không có lịch sử sẽ có toàn bộ cột tương ứng bằng null. Giữ nguyên null và thêm cờ sự hiện diện, không điền 0. LightGBM học được hướng rẽ của nhánh thiếu, nên chính sự vắng mặt trở thành đặc trưng có ích cho nhóm khách hồ sơ mỏng — nhóm trọng tâm của bài toán này.

## Đặc tả huấn luyện

## Chia dữ liệu ba tầng

| Tầng | Tỷ lệ | Số đơn Mục đích | Số lần truy cập |
| --- | --- | --- | --- |
| Holdout | 20% 61.502 nghiệm thu cuối cùng |   | đúng một lần |
| Huấn luyện qua | 80% 246.009 so sánh mô hình, dò siêu |   | không giới hạn |
| CV |   | tham số |   |
| Fold hiệu chỉnh | 1 trong 5 | ~49.202 hiệu chỉnh xác suất | mỗi lần huấn |
|   | fold |   | luyện |


Holdout tách ở bước 4 của pipeline, trước mọi phép tính đặc trưng, và danh sách id được ghi ra tệp để cố định qua các lần chạy.

Lý do tách riêng holdout khỏi CV: sau nhiều lần thử nghiệm, điểm CV trở nên lạc quan vì chính các lựa chọn đã được tối ưu theo nó. Holdout giữ được tính độc lập chỉ khi không được dùng để ra bất kỳ quyết định nào.

## Phương pháp kiểm định chéo

Stratified K-fold với k bằng 5, phân tầng theo TARGET.

Không dùng kiểm định theo thời gian, vì application_train không có cột ngày tháng nào, và SK_ID_CURR không đảm bảo tăng theo thời gian nộp đơn. Dùng id làm thay thế cho trục thời gian là giả định không kiểm chứng được; nếu sai nó tạo ra tập kiểm tra lệch phân bố mà không phát hiện được. Tài liệu kết quả phải nêu rõ lý do này.

## Năm nguồn rò rỉ và biện pháp chặn

Dữ liệu nguồn đã neo sẵn tại thời điểm nộp đơn: mọi DAYS_* và MONTHS_BALANCE đều âm, tức chỉ chứa thông tin quá khứ. Rò rỉ vì vậy không đến từ dữ liệu mà từ quá trình xử lý.

| Nguồn | Biểu hiện | Biện pháp chặn |
| --- | --- | --- |
| Tổng hợp đặc trưng trước | AUC trên CV cao hơn | tách holdout ở bước 4, trước |
| khi chia dữ liệu | holdout 0,02–0,05 | bước 5 |
| Target encoding tính ngoài | AUC CV rất cao, holdout | tính encoding bên trong từng |
| fold | sụt mạnh | fold qua Pipeline |
| Điền thiếu bằng thống kê | rò rỉ nhỏ nhưng có hệ | đưa imputer vào Pipeline , fit |
| toàn tập | thống | trong fold |
| Chuẩn hóa tính trên toàn | rò rỉ nhỏ | fit chỉ trên phần huấn luyện |
| tập |   | của fold |
| Cột trùng lặp hoặc sao | hai cột tương quan tuyệt | gate tương quan và gate AUC |
| chép nhãn | đối bằng 1 | đơn biến ở bước 6 |

## Ràng buộc kỹ thuật: mọi phép biến đổi phụ thuộc dữ liệu phải nằm trong

sklearn.pipeline.Pipeline , không chạy rời trước vòng CV. Điều này áp cho imputer,

scaler, encoder và mọi bước chọn đặc trưng.

## Hai kiểm định bắt buộc

Kiểm định AUC đơn biến. Với mỗi cột trong ma trận, tính roc_auc_score(y, col) . Cột vượt 0,95 phải điều tra trước khi huấn luyện. Chạy tự động ở gate bước 6.


Kiểm định bỏ đặc trưng. Với 5 đặc trưng có độ quan trọng cao nhất, huấn luyện lại mỗi lần loại một đặc trưng và ghi lại AUC. Kết quả đưa vào tài liệu dưới dạng bảng. Mục đích: phát hiện trường hợp một đặc trưng đơn lẻ gánh phần lớn hiệu năng, vì đó thường là dấu hiệu của rò rỉ hoặc của một biến thay thế nhãn.

## Trình tự mô hình

| Bước Mô hình |   | Mục đích | AUC tham |
| --- | --- | --- | --- |
|   |   |   | chiếu |
| 0 | dự đoán hằng số theo tỷ lệ cơ sở | mốc chặn dưới | 0,500 |
| 1 | hồi quy logistic chỉ với EXT_SOURCE_* | đo sức mạnh điểm bên | ~0,70 |
|   |   | thứ ba |   |
| 2 | hồi quy logistic với application và | mốc cơ sở giải thích | ~0,74 |
|   | họ tỷ lệ | được |   |
| 3 | LightGBM với toàn bộ đặc trưng | mô hình chính | 0,78–0,79 |
| 4 | LightGBM không dùng EXT_SOURCE_* | đo tín hiệu nội bộ | ~0,74 |

Bước 0 và 1 bắt buộc phải chạy và báo cáo. Thiếu chúng, con số cuối cùng không có hệ quy chiếu để đánh giá.

Khoảng AUC hợp lý cho bộ dữ liệu này là 0,74 đến 0,80. Giá trị vượt 0,85 phải được coi là cảnh báo rò rỉ và điều tra, không phải kết quả tốt.

## Đặc tả đánh giá

## Chỉ số kỹ thuật

| Chỉ số | Dùng để | Ghi chú |
| --- | --- | --- |
| AUC ROC | so sánh mô hình, báo cáo | chỉ đo khả năng xếp hạng |
|   | chính |   |
| PR-AUC | đánh giá trên lớp thiểu số | nhạy hơn AUC khi mất cân bằng |
| Brier score | đo độ chính xác của xác | bắt buộc sau hiệu chỉnh |
|   | suất |   |
| Reliability | kiểm tra hiệu chỉnh trực | bắt buộc đưa vào tài liệu |
| diagram | quan |   |


| Chỉ số | Dùng để | Ghi chú |
| --- | --- | --- |
| Accuracy | không dùng | 91,93% đạt được bằng cách đoán tất cả |
|   |   | bằng 0 |

## Độ chính xác của ước lượng

Kích thước holdout quyết định mức chính xác của con số báo cáo. Tính theo công thức Hanley–McNeil, quanh mức AUC 0,78:

|   | Tỷ lệ holdout Số đơn Số ca dương Sai số chuẩn Khoảng tin cậy 95% |   |
| --- | --- | --- |
| 10% 30.751 | 2.482 | 0,0056 0,769 – 0,791 |
| 20% 61.502 | 4.964 | 0,0040 0,772 – 0,788 |
| 30% 92.253 | 7.447 | 0,0032 0,774 – 0,786 |

Chọn 20%. Ở mức này, khoảng tin cậy rộng khoảng 0,016, đủ để phân biệt hai mô hình chên lệch 0,01 AUC một cách có ý nghĩa. Nhờ vậy việc chọn mô hình dựa trên bằng chứng, không dựa trên dao động ngẫu nhiên.

Mọi con số AUC trong tài liệu kết quả phải ghi kèm khoảng tin cậy.

## Hiệu chỉnh xác suất

Quyết định cấp tín dụng cần xác suất đúng thang đo, không chỉ cần thứ tự xếp hạng. LightGBM kết hợp trọng số lớp cho ra xác suất lệch cao hơn thực tế, nên bước hiệu chỉnh là bắt buộc.

- Phương pháp: isotonic regression, phù hợp vì số mẫu lớn.

- Dữ liệu hiệu chỉnh: fold riêng, không dùng dữ liệu đã huấn luyện.

- Kiểm chứng: Brier score và reliability diagram. AUC không đổi sau hiệu chỉnh vì thứ tự xếp hạng không đổi; dùng AUC để kiểm tra hiệu chỉnh là sai.

## Quy đổi sang điểm tín dụng

Xác suất sau hiệu chỉnh được quy đổi sang thang điểm theo công thức chuẩn của ngành:

\text{Score} = \text{Offset} - \text{Factor} \times \ln\!\left(\frac{p}{1- p}\right)

Tham số chọn sao cho tỷ lệ odds nhân đôi sau mỗi 20 điểm, neo tại 600 điểm. Điểm sau đó chia thành năm dải A đến E để đổ vào Dim_RiskBand .


## Chỉ số nghiệp vụ

Ngưỡng quyết định chọn theo chi phí sai lầm, không dùng mặc định 0,5. Cấu trúc chi phí giả định như sau, và phải được nêu rõ là giả định trong mọi báo cáo:

| Loại sai | Chi phí ước tính |
| --- | --- |
| Từ chối một khách không vỡ nợ | AMT_CREDIT × biên lợi nhuận |
| Duyệt một khách vỡ nợ | AMT_CREDIT × tỷ lệ tổn thất khi vỡ nợ |

Từ cấu trúc này, hệ thống sinh ra đường tổn thất theo ngưỡng và xác định ngưỡng tối ưu.

Ba chỉ số báo cáo kèm theo:

- 1. Tỷ lệ duyệt tại ngưỡng đã chọn.

- 2. Tỷ lệ vỡ nợ trong nhóm được duyệt, so với 8,07% của toàn bộ.

- 3. Bảng phân vị mười phần, hiển thị tỷ lệ vỡ nợ thực tế theo từng decile điểm. Điều kiện chấp nhận: tỷ lệ phải giảm đơn điệu từ decile rủi ro cao nhất xuống thấp nhất.

Bảng decile là chỉ số dễ đọc nhất với người không làm kỹ thuật, vì nó trả lời trực tiếp câu hỏi từ chối 10% rủi ro nhất thì tránh được bao nhiêu phần vỡ nợ.

## Kiểm tra công bằng

Dữ liệu chứa CODE_GENDER và DAYS_BIRTH . Cho vay tiêu dùng chịu ràng buộc pháp lý về phân biệt đối xử theo giới tính và tuổi ở nhiều thị trường, nên ba phép đo sau là bắt buộc, tính trên holdout:

| Phép đo | Câu hỏi |
| --- | --- |
| Tỷ lệ duyệt theo nhóm | nhóm nào bị từ chối nhiều hơn tại cùng một ngưỡng |
| AUC theo nhóm | mô hình có chính xác đều giữa các nhóm không |
| Độ hiệu chỉnh theo nhóm PD dự báo có khớp tỷ lệ vỡ nợ thực tế trong từng |   |
|   | nhóm không |

Phép thứ ba quan trọng nhất: nếu mô hình ước lượng rủi ro của một nhóm cao hơn thực tế, nhóm đó bị định giá bất lợi một cách có hệ thống dù rủi ro thực tương đương. Đây là bất công đo được bằng số liệu.

Phạm vi dừng ở đo và báo cáo. Khắc phục thiên lệch không nằm trong phạm vi, nhưng kết quả đo phải được công bố kể cả khi bất lợi.


## Lớp phục vụ và dashboard

## Nạp dữ liệu vào SQL Server

Mỗi lần chạy, pipeline ghi vào bảng tạm stg_* trước, sau đó đổi tên trong một giao dịch duy nhất. Bảng đích không bao giờ ở trạng thái dở dang khi Power BI đang đọc.

## Ba ràng buộc kỹ thuật:

- 1. Độ dài cột chuỗi khai báo theo giá trị thực tế, không đặt NVARCHAR(4000) cho mọi cột. Cột quá dài vượt giới hạn khóa 1700 byte và không index được.

- 2. Tạo PRIMARY KEY và FOREIGN KEY thật sau khi đổi tên. Ràng buộc ở tầng cơ sở dữ liệu bắt được lỗi mà kiểm tra ở tầng ứng dụng bỏ sót.

- 3. Một biến môi trường duy nhất cho cổng kết nối, dùng chung cho docker-compose , script nạp và chuỗi kết nối Power BI. Lệch cổng giữa ba nơi này là lỗi thường gặp và khó phát hiện.

## Các trang báo cáo

| Trang | Câu hỏi trả lời | Nội dung chính |
| --- | --- | --- |
| Danh mục | cơ cấu đơn vay như thế | số đơn, giá trị, tỷ lệ vỡ nợ theo loại hợp |
|   | nào | đồng, nghề, trình độ |
| Yếu tố rủi ro | nhóm nào rủi ro hơn | tỷ lệ vỡ nợ theo nhóm tuổi, thu nhập, hình |
|   |   | thức cư trú, tình trạng hôn nhân |
| Chất lượng mô | mô hình hoạt động tốt | bảng decile, reliability diagram, AUC trên |
| hình | đến đâu | holdout |
| Ngưỡng quyết | nên đặt ngưỡng ở đâu | tham số what-if, tỷ lệ duyệt và tổn thất dự |
| định |   | kiến theo ngưỡng |

Trang Ngưỡng quyết định là thành phần biến báo cáo thành công cụ ra quyết định: một tham số what-if điều chỉnh ngưỡng PD, hai measure tính tỷ lệ duyệt và tổn thất dự kiến tương ứng.

Trang Chất lượng mô hình chỉ đọc dữ liệu có IsHoldout = 1 , vì đây là phần duy nhất mô hình chưa từng thấy.


## Measure cần có

| Measure | Công thức | Định dạng |
| --- | --- | --- |
| Tỷ lệ vỡ nợ thực tế | DIVIDE(SUM(TARGET), | phần trăm |
|   | COUNTROWS(Fact_Application)) |   |
| PD trung bình | AVERAGE(PD_Predicted) | phần trăm |
| Chênh lệch hiệu | [PD trung bình] - [Tỷ lệ vỡ nợ thực tế] | điểm phần |
| chỉnh |   | trăm |
| Tỷ lệ duyệt | DIVIDE(COUNTROWS(FILTER(..., PD < | phần trăm |
|   | Ngưỡng)), COUNTROWS(...)) |   |
| Số đơn vay | COUNTROWS(Fact_Application) | số nguyên |

Measure Chênh lệch hiệu chỉnh là thành phần quan trọng nhất của trang chất lượng mô hình: nó cho thấy mô hình ước lượng cao hay thấp hơn thực tế trong từng lát cắt. Cắt theo giới tính và nhóm tuổi, chính measure này thực hiện phép kiểm tra công bằng thứ ba ở mục đánh giá.

## Bốn quy tắc cho mô hình ngữ nghĩa

- 1. Mọi quan hệ là một chiều, từ bảng fact sang dimension. Quan hệ hai chiều làm mẫu số của các measure tỷ lệ bị lọc theo điều kiện của tử số, cho ra kết quả bằng 100%.

- 2. Quan hệ tạo thủ công, không dùng tính năng tự động phát hiện.

- 3. Ngưỡng trong biểu thức DAX viết dưới dạng phân số. Hàm DIVIDE trả về giá trị trong khoảng 0 đến 1, nên điều kiện so sánh phải viết > 0.07 , không viết > 7 . Định dạng phần trăm đặt ở thuộc tính hiển thị.

- 4. Tắt tính năng ngày tháng tự động. Dữ liệu không có cột ngày nào, nên tính năng này chỉ sinh bảng ẩn vô ích và làm phình mô hình.

Riêng với cột cờ và cột tỷ lệ như TARGET , PD_Predicted , CREDIT_INCOME_RATIO , đặt thuộc tính tổng hợp mặc định là không tổng hợp. Để mặc định là tính tổng sẽ cho ra con số vô nghĩa khi kéo vào biểu đồ.

## Về dữ liệu cá nhân

Bộ dữ liệu không chứa tên, số điện thoại hay địa chỉ. Định danh duy nhất là SK_ID_CURR , một số nguyên vô danh. Báo cáo vì vậy có thể công bố công khai mà không phát sinh rủi ro dữ liệu cá nhân. Không bổ sung tên giả cho mục đích trình bày, vì điều đó tạo ấn tượng sai rằng báo cáo chứa hồ sơ khách hàng thật.


## Lộ trình triển khai

Sáu giai đoạn, mỗi giai đoạn kết thúc bằng một điều kiện kiểm chứng được bằng mã chạy tự động. Giai đoạn không qua cổng thì không chuyển tiếp, vì mọi giai đoạn sau đều dựa trên kết quả của nó.

## ai doan két thuc bing mdt cong kiém tra do dugc

lộ trình 6 tuần · 6 cổng kiểm tra

Thứ tự hai giai đoạn giữa là ràng buộc có chủ đích: mốc cơ sở và kiểm định rò rỉ đứng trước mô hình chính. Lý do: một kết quả cao đạt được trước khi có hệ quy chiếu rất khó được xem xét lại một cách khách quan.

Nếu thời gian rút xuống ba tuần, giữ nguyên giai đoạn 1 đến 4 và bỏ giai đoạn 5 cùng phần công bằng của giai đoạn 6. Pipeline đúng kèm mô hình đã kiểm định rò rỉ là phần lõi; dashboard là lớp trình bày bên trên.

## Tiêu chí nghiệm thu

Hệ thống được coi là hoàn thành khi thỏa đủ mười bốn điều kiện sau. Mỗi điều kiện kiểm chứng được bằng cách chạy mã hoặc đọc tài liệu, không dựa trên đánh giá chủ quan.


## Về pipeline

- Chạy lại toàn bộ từ dữ liệu thô trên máy sạch bằng một lệnh duy nhất

- Không bước nào ghi đè đầu vào của chính nó; chạy hai lần cho kết quả giống nhau

- Toàn bộ quality gate ở bước 2, 3, 4, 5, 6, 8 đều đạt

- Logic sản xuất nằm trong module Python import được, không nằm trong notebook

- Phiên bản thư viện được pin; môi trường tái tạo được trên máy khác

## Về tính đúng đắn của mô hình

- Holdout được tách trước mọi phép tính đặc trưng, và chỉ được đọc một lần

- Kiểm định AUC đơn biến đã chạy; không cột nào vượt 0,95

- Kiểm định bỏ đặc trưng đã chạy cho 5 đặc trưng mạnh nhất, kết quả đưa vào tài liệu

- Mọi phép biến đổi phụ thuộc dữ liệu nằm trong Pipeline , không chạy trước CV

- AUC trên holdout nằm trong khoảng 0,74–0,80, hoặc có giải trình nếu vượt

## Về kết quả báo cáo

- Đã báo cáo mốc cơ sở: tỷ lệ nền và mô hình chỉ dùng EXT_SOURCE_*

- Xác suất đã hiệu chỉnh, có reliability diagram và Brier score

- Ngưỡng quyết định gắn với cấu trúc chi phí, kèm bảng decile

- Mọi con số AUC ghi kèm khoảng tin cậy

- Đã đo và công bố ba phép kiểm tra công bằng theo giới tính và nhóm tuổi

## Về lớp phục vụ

- Mọi quan hệ trong mô hình ngữ nghĩa là một chiều, mọi ngưỡng DAX dạng phân số

- Bốn trang báo cáo hoạt động, đọc trực tiếp từ SQL Server

## Về tài liệu

Tài liệu kết quả phải nêu rõ ba giới hạn đã xác định ở mục tổng quan: dữ liệu không có ngày tháng tuyệt đối nên không kiểm định được theo thời gian; ngưỡng X và Y của nhãn không được công bố nên xác suất không quy đổi trực tiếp sang PD chuẩn ngành; và application_test.csv không có nhãn nên mọi đo lường dựa trên holdout tự tách.

Phần số liệu trong tài liệu sinh tự động từ kết quả pipeline, không chép thủ công. Một script đọc chỉ số từ MLflow và ghi vào tài liệu giữa hai dòng đánh dấu là đủ. Điều này loại bỏ khả năng tài liệu lệch khỏi mã sau mỗi lần chạy lại.
