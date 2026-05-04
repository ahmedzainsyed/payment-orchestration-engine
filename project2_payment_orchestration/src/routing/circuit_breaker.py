"""Per-gateway circuit breaker: CLOSED → OPEN → HALF_OPEN → CLOSED"""
import time
from enum import Enum
from typing import Dict
import structlog

log = structlog.get_logger()

class CBState(Enum):
    CLOSED    = "closed"
    OPEN      = "open"
    HALF_OPEN = "half_open"

class GatewayCircuitBreaker:
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 30):
        self.failure_threshold = failure_threshold
        self.recovery_timeout  = recovery_timeout
        self._failures: Dict[str, int]       = {}
        self._state:    Dict[str, CBState]   = {}
        self._opened:   Dict[str, float]     = {}

    def _init(self, gw: str):
        if gw not in self._state:
            self._failures[gw] = 0
            self._state[gw]    = CBState.CLOSED
            self._opened[gw]   = 0.0

    def is_available(self, gw: str) -> bool:
        self._init(gw)
        s = self._state[gw]
        if s == CBState.CLOSED:
            return True
        if s == CBState.OPEN:
            if time.time() - self._opened[gw] >= self.recovery_timeout:
                self._state[gw] = CBState.HALF_OPEN
                log.info("circuit_half_open", gw=gw)
                return True
            return False
        return True   # HALF_OPEN: allow probe

    def record_success(self, gw: str):
        self._init(gw)
        if self._state[gw] == CBState.HALF_OPEN:
            log.info("circuit_closed", gw=gw)
        self._failures[gw] = 0
        self._state[gw] = CBState.CLOSED

    def record_failure(self, gw: str):
        self._init(gw)
        self._failures[gw] += 1
        if self._state[gw] == CBState.HALF_OPEN:
            self._state[gw]  = CBState.OPEN
            self._opened[gw] = time.time()
            log.warning("circuit_reopened", gw=gw)
            return
        if self._failures[gw] >= self.failure_threshold:
            self._state[gw]  = CBState.OPEN
            self._opened[gw] = time.time()
            log.warning("circuit_opened", gw=gw, failures=self._failures[gw])

    def status(self) -> Dict[str, str]:
        return {gw: s.value for gw, s in self._state.items()}
