# Báo Cáo Sự Cố Dữ Liệu (Incident Report)

## Severity
P1

## Summary
Trong đợt vận hành pipeline, hệ thống ghi nhận đồng thời 3 sự cố: trùng lặp khóa chính (`order_id`) ở tầng ingestion, lỗi join fanout do bảng chiều `customers` có nhiều bản ghi active làm nhân đôi doanh thu `fct_daily_revenue`, và tài liệu Knowledge Base bị trễ timestamp 3 tiếng ảnh hưởng đến RAG pipeline. Toàn bộ sự cố đã được phát hiện, chặn đứng và khắc phục thành công.

## Detection
- **Signal**:
  - Contract check báo lỗi Uniqueness trên `order_id` ở mức `critical` $\rightarrow$ Kích hoạt action `BLOCK`.
  - dbt unit test `expose_duplicate_active_customer_revenue_inflation` bắt lỗi sai lệch doanh thu ($200 vs $100).
  - Freshness monitor phát hiện KB documents trễ 190 phút (vượt ngưỡng 60 phút).
- **First observed time**: 2026-08-29T15:00:00Z.

## Root Cause
1. **Duplicate PK**: Nguồn upstream retry gửi lại batch dữ liệu không có idempotency key dẫn đến trùng 3 dòng `order_id`.
2. **SCD2 Customer Fanout**: Bảng chiều `stg_customers` chứa nhiều phiên bản active (`is_active = true`) cho cùng một `customer_id`, khiến câu lệnh `LEFT JOIN` trong `fct_daily_revenue` bị nhân bản dòng giao dịch.
3. **Stale KB**: Tiến trình đồng bộ tài liệu kiến thức bị treo, làm trễ dữ liệu 3 giờ so với thời gian thực.

## Evidence
1. **Contract Check Failure**:
   ```text
   expect_column_values_to_be_unique (order_id) -> FAILED (critical)
   Determined Pipeline Action: BLOCK
   ```
2. **dbt Unit Test Failure Log**:
   ```text
   order_date: 2026-08-01 | completed_order_rows: expected 1 -> actual 2 | daily_revenue: expected 100.0 -> actual 200.0
   ```
3. **Freshness Delay & SLO Burn Rate**:
   - `KB freshness minutes`: 190.0m (vượt ngưỡng cho phép 60m).
   - `SLO burn rate`: 4.0x (tiêu hao ngân sách lỗi ở mức cảnh báo).

## Blast Radius
```text
raw_orders / raw_customers / kb_documents
      │
      ▼
┌───────────────┐        ┌──────────────────┐
│  stg_orders   │        │  stg_customers   │
└───────┬───────┘        └────────┬─────────┘
        │                         │
        └───────────┬─────────────┘
                    ▼
       ┌────────────────────────┐
       │   fct_daily_revenue    │
       └────────────┬───────────┘
                    ▼
       ┌────────────────────────┐
       │ ceo_revenue_dashboard │ (Báo cáo doanh thu điều hành)
       └────────────────────────┘
```

## Mitigation
1. Kích hoạt cơ chế `BLOCK` tại tầng Ingestion Contract để ngăn dữ liệu trùng lặp đi vào Data Warehouse.
2. Sửa câu lệnh SQL trong `fct_daily_revenue.sql` sử dụng `SELECT DISTINCT customer_id` từ `active_customers` nhằm triệt tiêu join fanout.
3. Khởi động lại worker đồng bộ tài liệu Knowledge Base.

## Recovery
1. Chạy `scripts/reset_lab.py` để làm sạch dữ liệu đầu vào.
2. Chạy `dbt build` xác nhận 19/19 nodes (models, data tests, unit tests) đều pass 100%.
3. Chạy `scripts/run_baseline.py` xác nhận toàn bộ chỉ số độ tin cậy trở về trạng thái khỏe mạnh.

## Verification
- [x] Contract healthy (0 failed checks, action: PASS)
- [x] dbt tests healthy (19/19 nodes passed)
- [x] Anomaly returned to expected range
- [x] SLO healthy / budget understood (burn_rate: 0.0)
- [x] Downstream output verified (doanh thu và số đơn khớp hoàn toàn giữa staging và mart)

## Prevention / Action Items
| Action | Owner | Deadline | Why |
|---|---|---|---|
| Bắt buộc kiểm tra Contract & GX Checkpoint ở Ingestion Gate | Data Eng | 2026-09-05 | Chặn đứng dữ liệu sai định dạng/trùng lặp ngay tại cửa ngõ |
| Thêm dbt singular test và unit test SCD2 vào CI/CD pipeline | Analytics Eng | 2026-09-06 | Tự động phát hiện lỗi fanout doanh thu trước khi deploy code |
| Thiết lập cảnh báo Multi-Window Multi-Burn-Rate | Observability/SRE | 2026-09-08 | Tránh báo động giả (transient spikes), chỉ page khi có fast burn |
