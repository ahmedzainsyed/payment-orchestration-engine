"""Rolling P95 latency monitor per gateway."""
import numpy as np
from collections import deque
from typing import Dict

class LatencyProber:
    def __init__(self, window: int = 100):
        self._lat: Dict[str, deque] = {}
        self._w = window

    def record(self, gw: str, ms: float):
        if gw not in self._lat:
            self._lat[gw] = deque(maxlen=self._w)
        self._lat[gw].append(ms)

    def p95(self, gw: str) -> float:
        if gw not in self._lat or len(self._lat[gw]) < 5:
            return 500.0
        return float(np.percentile(list(self._lat[gw]), 95))

    def penalty(self, gw: str) -> float:
        p = self.p95(gw)
        return 0.0 if p <= 100 else min((p - 100) / 900, 1.0)

    def summary(self) -> Dict[str, float]:
        return {gw: round(self.p95(gw), 1) for gw in self._lat}
