"""MDR-aware cost model for routing reward computation."""
from config.settings import settings

class CostModel:
    def adjusted_reward(self, gateway: str, method: str, amount: float, success: bool) -> float:
        if not success:
            return 0.0
        mdr = settings.MDR_RATES.get(gateway, {}).get(method, 0.02)
        penalty = mdr * min(amount / 50_000, 1.0)
        return max(1.0 - penalty, 0.1)

    def expected_cost(self, gateway: str, method: str, amount: float) -> float:
        mdr = settings.MDR_RATES.get(gateway, {}).get(method, 0.02)
        return round(amount * mdr, 2)
