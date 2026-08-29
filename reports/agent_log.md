# AI Agent Decision Log

Ghi lại 3 quyết định kỹ thuật cốt lõi trong quá trình thiết kế và bảo vệ hệ thống Data Reliability.

---

## Decision 1: Bảo vệ tầng Transformation bằng dbt Unit Test chống SCD2 Fanout
- **Hypothesis**: `not_null/unique` là data tests kiểm tra dữ liệu thực tế runtime, không kiểm tra được lỗi logic trong SQL. Bảng chiều `customers` có nhiều phiên bản active (`is_active = true`) sẽ gây join fanout nhân đôi doanh thu nếu không có unit test phát hiện và deduplicate.
- **Prompt / request to agent**: Thêm generic test, singular test, giải thích sự khác biệt giữa data test và unit test, và viết unit test nhỏ nhất phát hiện lạm phát doanh thu do lỗi SCD2.
- **Agent proposal**:
  1. Bổ sung generic tests `unique`/`not_null` và singular test `assert_completed_order_count_matches_stg.sql`.
  2. Viết dbt unit test `expose_duplicate_active_customer_revenue_inflation` với mock data gồm 2 dòng active của 1 khách hàng và 1 đơn hàng $100.
  3. Sửa `fct_daily_revenue.sql` sử dụng `SELECT DISTINCT customer_id` trong CTE `active_customers`.
- **Evidence/test**:
  - Khi chưa sửa SQL: unit test fail rõ ràng (actual: 2 dòng / $200 vs expected: 1 dòng / $100).
  - Sau khi sửa SQL: `dbt build` chạy thành công toàn bộ 19/19 nodes (seeds, models, data tests, singular tests, unit tests).
- **Accept / reject / revise**: Accept.
- **Why**: Ngăn chặn rủi ro sai lệch số liệu doanh thu nghiêm trọng trên CEO Dashboard do lỗi mô hình dữ liệu SCD Type 2.

---

## Decision 2: Anomaly Detection theo Ngữ cảnh & Cảnh báo SRE Multi-Window Multi-Burn-Rate
- **Hypothesis**: Z-score thông thường dễ bị sai khi dữ liệu có tính chu kỳ (seasonality theo ngày trong tuần) hoặc chứa outlier. Cảnh báo lỗi dựa trên 1 cửa sổ đơn lẻ cũng dễ gây alert fatigue do các đột biến ngắn hạn (transient spikes).
- **Prompt / request to agent**: Nâng cấp `detect_anomaly(method="auto")` xử lý seasonality/outlier và cài đặt `evaluate_multiwindow_burn` theo nguyên lý Google SRE.
- **Agent proposal**:
  1. Cài đặt `mad_detector` (Median Absolute Deviation) xử lý trường hợp `MAD = 0` và tự động phân khúc dữ liệu theo `day_of_week`.
  2. Cài đặt chính sách đánh giá đa cửa sổ: chỉ gửi page khi cả short window và long window cùng vượt ngưỡng (sustained fast burn), và hạ mức cảnh báo với đột biến ngắn hạn (transient spike).
- **Evidence/test**:
  - Chạy lỗi `volume_drop`: Anomaly detector bắt chính xác `is_anomaly = True` (score = 5.53).
  - `pytest tests_public/test_slo.py` và `test_anomaly.py` đều pass 100%.
- **Accept / reject / revise**: Accept.
- **Why**: Loại bỏ báo động giả khi lưu lượng thay đổi tự nhiên theo ngày trong tuần và bảo vệ đội ngũ on-call khỏi tình trạng quá tải thông báo.
