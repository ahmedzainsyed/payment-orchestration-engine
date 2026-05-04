"""
LinUCB Disjoint Contextual Bandit.
Each gateway arm learns independently from transaction context.

Score = θ_a·x  +  α·√(x^T A_a^{-1} x)
         exploit        explore
"""
import json
import numpy as np
from typing import Dict, List, Optional
import structlog

log = structlog.get_logger()


class LinUCBArm:
    def __init__(self, arm_id: str, d: int, alpha: float):
        self.arm_id = arm_id
        self.alpha  = alpha
        self.d      = d
        self.A      = np.identity(d)     # feature covariance
        self.b      = np.zeros((d, 1))   # reward accumulator

    def score(self, x: np.ndarray) -> float:
        A_inv = np.linalg.inv(self.A)
        theta = A_inv @ self.b
        x = x.reshape(-1, 1)
        exploit = float((theta.T @ x).squeeze())
        explore = self.alpha * float(np.sqrt((x.T @ A_inv @ x).squeeze()))
        return exploit + explore

    def update(self, x: np.ndarray, reward: float):
        x = x.reshape(-1, 1)
        self.A += x @ x.T
        self.b += reward * x

    def to_dict(self) -> dict:
        return {"A": self.A.tolist(), "b": self.b.tolist()}

    @classmethod
    def from_dict(cls, arm_id: str, d: int, alpha: float, data: dict) -> "LinUCBArm":
        arm = cls(arm_id, d, alpha)
        arm.A = np.array(data["A"])
        arm.b = np.array(data["b"])
        return arm


class LinUCBRouter:
    """Multi-arm bandit gateway router."""

    def __init__(self, gateways: List[str], context_dim: int, alpha: float = 0.5):
        self.gateways    = gateways
        self.context_dim = context_dim
        self.alpha       = alpha
        self.arms: Dict[str, LinUCBArm] = {
            g: LinUCBArm(g, context_dim, alpha) for g in gateways
        }
        self.total_rounds = 0
        log.info("linucb_init", gateways=gateways, alpha=alpha)

    def select(self, context: np.ndarray, exclude: Optional[List[str]] = None) -> str:
        exclude = exclude or []
        scores  = {
            gw: arm.score(context)
            for gw, arm in self.arms.items()
            if gw not in exclude
        }
        if not scores:
            return self.gateways[0]
        selected = max(scores, key=scores.get)
        log.debug("gateway_selected", gw=selected,
                  scores={k: round(v, 3) for k, v in scores.items()})
        return selected

    def update(self, gateway: str, context: np.ndarray, reward: float):
        self.arms[gateway].update(context, reward)
        self.total_rounds += 1

    def q_values(self) -> Dict[str, float]:
        dummy = np.ones(self.context_dim)
        return {gw: round(arm.score(dummy), 4) for gw, arm in self.arms.items()}

    def serialize(self) -> str:
        return json.dumps({
            "total_rounds": self.total_rounds,
            "arms": {gw: arm.to_dict() for gw, arm in self.arms.items()}
        })

    def deserialize(self, blob: str):
        data = json.loads(blob)
        self.total_rounds = data["total_rounds"]
        for gw, arm_data in data["arms"].items():
            if gw in self.arms:
                self.arms[gw] = LinUCBArm.from_dict(
                    gw, self.context_dim, self.alpha, arm_data
                )
        log.info("bandit_restored", rounds=self.total_rounds)
