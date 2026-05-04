"""
Payment Orchestration API
Start: uvicorn src.api.app:app --host 0.0.0.0 --port 8001 --workers 2
"""
import time
import structlog
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.responses import Response
from contextlib import asynccontextmanager
from prometheus_client import (
    generate_latest, CONTENT_TYPE_LATEST,
    Counter, Histogram, Gauge
)

from config.settings import settings
from src.api.schemas import PaymentRequest, PaymentResponse
from src.routing.router import PaymentOrchestrator

log = structlog.get_logger()

PAYMENT_TOTAL  = Counter("payments_total", "Total payments", ["gateway", "outcome"])
PAYMENT_LAT    = Histogram("payment_latency_ms", "E2E latency",
                           buckets=[50,100,200,300,500,750,1000,2000])
RETRY_TOTAL    = Counter("payment_retries_total", "Retries", ["gateway"])
CB_STATE       = Gauge("circuit_breaker_open", "CB open=1", ["gateway"])
BANDIT_ROUNDS  = Gauge("bandit_total_rounds", "Bandit learning rounds")

orchestrator: PaymentOrchestrator = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global orchestrator
    orchestrator = PaymentOrchestrator()
    yield

app = FastAPI(title="Payment Orchestration API", version="2.0.0", lifespan=lifespan)

def auth(x_api_key: str = Header(...)):
    if x_api_key != settings.API_SECRET_KEY:
        raise HTTPException(401, "Unauthorized")

@app.get("/health")
async def health():
    return {
        "status":           "ok",
        "bandit_rounds":    orchestrator.router.total_rounds,
        "gateway_scores":   orchestrator.router.q_values(),
        "circuit_breakers": orchestrator.cb.status(),
        "latency_p95_ms":   orchestrator.latency.summary(),
    }

@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

@app.post("/v1/pay", response_model=PaymentResponse)
async def pay(req: PaymentRequest, _=Depends(auth)):
    import time as t
    start = t.perf_counter()
    txn = req.model_dump()
    txn["hour"] = txn.get("hour") or __import__("time").localtime().tm_hour

    result = await orchestrator.process(txn)

    elapsed = (t.perf_counter() - start) * 1000
    PAYMENT_LAT.observe(elapsed)
    BANDIT_ROUNDS.set(result["bandit_rounds"])

    for h in result["history"]:
        PAYMENT_TOTAL.labels(
            gateway=h["gateway"],
            outcome="success" if h["success"] else "failure"
        ).inc()

    # Retries = all attempts except last (if last was retry)
    for h in result["history"][:-1]:
        if not h["success"]:
            RETRY_TOTAL.labels(gateway=h["gateway"]).inc()

    for gw, state in result["circuit_breakers"].items():
        CB_STATE.labels(gateway=gw).set(0 if state == "closed" else 1)

    log.info("payment", txn_id=req.transaction_id,
             status=result["final_status"], attempts=result["attempts"],
             ms=round(elapsed, 1))

    return PaymentResponse(transaction_id=req.transaction_id, **result)

@app.post("/v1/admin/downtime/{gateway}")
async def trigger_downtime(gateway: str, duration: int = 30, _=Depends(auth)):
    """Simulate gateway downtime — tests circuit breaker."""
    from src.gateway.mock_gateways import gateway_simulator
    gateway_simulator.trigger_downtime(gateway, float(duration))
    return {"message": f"{gateway} down for {duration}s"}
