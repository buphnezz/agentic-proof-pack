from prometheus_client import Counter, Histogram, Gauge

REQS = Counter("app_requests_total", "Total requests", ["route"])
FAILS = Counter("app_failures_total", "Total failures", ["route", "reason"])
AUTH_FAILS = Counter("app_auth_failures_total", "Auth failures", ["route", "mode"])

LAT = Histogram(
    "app_latency_ms",
    "Latency in ms",
    ["route"],
    buckets=[50,100,200,300,500,800,1200,2000,3000,5000,8000]
)

GROUNDED = Gauge("app_grounded_ratio", "Grounded ratio of last response", ["route"])
REPAIRS = Counter("app_schema_repairs_total", "Schema repair attempts", ["route"])
