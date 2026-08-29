-- Singular data test: Total completed order rows and revenue in fct_daily_revenue
-- must strictly match total completed orders and revenue in stg_orders.
-- If the customer join produces a fanout/inflation, this test fails by returning rows.
with mart_total as (
    select
        coalesce(sum(completed_order_rows), 0) as total_mart_orders,
        coalesce(sum(daily_revenue), 0.0) as total_mart_revenue
    from {{ ref('fct_daily_revenue') }}
),
staging_total as (
    select
        count(*) as total_stg_orders,
        coalesce(sum(amount_usd), 0.0) as total_stg_revenue
    from {{ ref('stg_orders') }}
    where status = 'completed'
)
select
    m.total_mart_orders,
    s.total_stg_orders,
    m.total_mart_revenue,
    s.total_stg_revenue
from mart_total m
cross join staging_total s
where m.total_mart_orders != s.total_stg_orders
   or abs(m.total_mart_revenue - s.total_stg_revenue) > 0.01
