from student_api import column_downstream, downstream_assets


def test_transitive_downstream_assets():
    graph = {
        "raw_orders": ["stg_orders"],
        "stg_orders": ["revenue"],
        "revenue": ["dashboard"],
    }
    assert downstream_assets(graph, "raw_orders") == ["stg_orders", "revenue", "dashboard"]


def test_transitive_column_downstream_assets():
    column_graph = {
        "stg_orders.amount": ["fct_daily_revenue.daily_revenue"],
        "fct_daily_revenue.daily_revenue": ["ceo_dashboard.kpi_revenue"],
    }
    assert column_downstream(column_graph, "stg_orders.amount") == [
        "fct_daily_revenue.daily_revenue",
        "ceo_dashboard.kpi_revenue",
    ]

