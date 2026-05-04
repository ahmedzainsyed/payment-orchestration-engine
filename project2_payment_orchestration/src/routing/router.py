"""
Payment Orchestrator — wires together LinUCB, circuit breaker, cost model, gateways.
"""
import asyncio, time
import numpy as np
from typing import Dict, Any, List
import structlog

from config.settings import settings
from src.bandit.linucb import LinUCBRouter
from src.bandit.state_manager import BanditStateManager
from src.routing.circuit_breaker import GatewayCircuitBreaker
from src.routing.cost_model import CostModel
from src.routing.latency_prober import LatencyProber
from src.gateway.mock_gateways import gateway_simulator

log = structlog.get_logger()

BANKS   = ["hdfc", "icici", "sbi", "axis", "kotak", "other"]
METHODS = ["upi", "card", "netbanking"]


def extract_context(txn: Dict[str, Any]) -> np.ndarray:
    """12-dim context vector for LinUCB."""
    hour   = int(txn.get("hour", 12))
    amount = float(txn.get("amount", 1000))
    bank   = txn.get("bank", "other")
    method = txn.get("payment_method", "upi")

    hour_sin = np.sin(2 * np.pi * hour / 24)
    hour_cos = np.cos(2 * np.pi * hour / 24)
    amt_log  = np.log1p(amount) / np.log1p(1_000_000)
    hi_amt   = float(amount > 50_000)

    bank_vec   = [float(bank == b) for b in BANKS[:4]]   # 4-dim
    method_vec = [float(method == m) for m in METHODS]   # 3-dim

    return np.array(
        [hour_sin, hour_cos, amt_log, hi_amt] + bank_vec + method_vec,
        dtype=np.float64
    )


class PaymentOrchestrator:
    def __init__(self):
        self.router   = LinUCBRouter(settings.GATEWAYS, settings.CONTEXT_DIM, settings.LINUCB_ALPHA)
        self.state_mgr = BanditStateManager()
        try:
            self.state_mgr.load(self.router)
        except Exception as e:
            log.warning("state_load_skipped", reason=str(e))

        self.cb      = GatewayCircuitBreaker(settings.CB_FAILURE_THRESHOLD, settings.CB_RECOVERY_TIMEOUT)
        self.cost    = CostModel()
        self.latency = LatencyProber()
        log.info("orchestrator_ready", gateways=settings.GATEWAYS)

    def _available(self, exclude: List[str]) -> List[str]:
        return [gw for gw in settings.GATEWAYS
                if gw not in exclude and self.cb.is_available(gw)]

    async def process(self, txn: Dict[str, Any]) -> Dict[str, Any]:
        ctx    = extract_context(txn)
        method = txn.get("payment_method", "upi")
        bank   = txn.get("bank", "other")
        amount = float(txn.get("amount", 1000))
        hour   = int(txn.get("hour", 12))

        history, tried, final_ok = [], [], False

        for attempt in range(settings.MAX_RETRY_ATTEMPTS + 1):
            available = self._available(exclude=tried)
            if not available:
                log.error("no_gateways_available", tried=tried)
                break

            gw = self.router.select(ctx, exclude=tried)
            tried.append(gw)

            resp = await gateway_simulator.call(gw, method, bank, amount, hour)
            self.latency.record(gw, resp.latency_ms)

            if resp.success:
                self.cb.record_success(gw)
            else:
                self.cb.record_failure(gw)

            reward = self.cost.adjusted_reward(gw, method, amount, resp.success)
            self.router.update(gw, ctx, reward)
            self.state_mgr.maybe_checkpoint(self.router)

            history.append({
                "attempt":    attempt + 1,
                "gateway":    gw,
                "success":    resp.success,
                "latency_ms": round(resp.latency_ms, 1),
                "error_code": resp.error_code,
                "cost_inr":   self.cost.expected_cost(gw, method, amount) if resp.success else 0,
            })

            if resp.success:
                final_ok = True
                break

            if attempt < settings.MAX_RETRY_ATTEMPTS:
                await asyncio.sleep(settings.RETRY_BACKOFF_BASE * (2 ** attempt))

        return {
            "final_status":     "success" if final_ok else "failed",
            "attempts":         len(history),
            "history":          history,
            "total_latency_ms": round(sum(h["latency_ms"] for h in history), 1),
            "gateway_scores":   self.router.q_values(),
            "circuit_breakers": self.cb.status(),
            "bandit_rounds":    self.router.total_rounds,
        }
