"""Realistic gateway simulators with per-bank, per-hour, latency variation."""
import random, time, asyncio
from dataclasses import dataclass
from typing import Dict

@dataclass
class GatewayResponse:
    success: bool
    latency_ms: float
    error_code: str = ""
    gateway: str = ""

class GatewaySimulator:
    CONFIGS = {
        "razorpay": {
            "base": {"upi": 0.94, "card": 0.88, "netbanking": 0.82},
            "bank":  {"hdfc": +0.03, "icici": +0.02, "sbi": -0.04, "axis": +0.01, "kotak": +0.01},
            "lat_mean": 120, "lat_std": 40,
        },
        "payu": {
            "base": {"upi": 0.91, "card": 0.85, "netbanking": 0.80},
            "bank":  {"hdfc": +0.01, "icici": +0.02, "sbi": -0.02, "axis": +0.02, "kotak": +0.01},
            "lat_mean": 150, "lat_std": 60,
        },
        "stripe": {
            "base": {"upi": 0.88, "card": 0.92, "netbanking": 0.78},
            "bank":  {"hdfc": +0.02, "icici": +0.01, "sbi": -0.01, "axis": +0.01, "kotak": +0.01},
            "lat_mean": 200, "lat_std": 80,
        },
        "cashfree": {
            "base": {"upi": 0.92, "card": 0.84, "netbanking": 0.81},
            "bank":  {"hdfc": +0.01, "icici": +0.02, "sbi": -0.03, "axis": +0.02, "kotak": +0.01},
            "lat_mean": 130, "lat_std": 50,
        },
    }

    def __init__(self):
        self._downtime: Dict[str, float] = {}

    def trigger_downtime(self, gw: str, seconds: float = 30.0):
        self._downtime[gw] = time.time() + seconds

    async def call(self, gateway: str, method: str, bank: str,
                   amount: float, hour: int) -> GatewayResponse:
        cfg = self.CONFIGS.get(gateway, self.CONFIGS["razorpay"])
        lat = max(random.gauss(cfg["lat_mean"], cfg["lat_std"]), 20.0)
        await asyncio.sleep(lat / 1000)

        if self._downtime.get(gateway, 0) > time.time():
            return GatewayResponse(False, lat, "GATEWAY_DOWN", gateway)

        prob = cfg["base"].get(method, 0.85)
        prob += cfg["bank"].get(bank, 0.0)
        if 2 <= hour <= 5:
            prob -= 0.05
        if amount > 50_000:
            prob -= 0.03
        prob = min(max(prob, 0.1), 0.99)

        ok = random.random() < prob
        return GatewayResponse(ok, lat, "" if ok else "BANK_DECLINED", gateway)

gateway_simulator = GatewaySimulator()
