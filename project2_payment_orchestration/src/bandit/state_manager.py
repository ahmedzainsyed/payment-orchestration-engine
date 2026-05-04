"""Redis persistence for bandit state."""
import redis
import structlog
from config.settings import settings
from src.bandit.linucb import LinUCBRouter

log = structlog.get_logger()
REDIS_KEY = "bandit:linucb:v1"
CHECKPOINT_EVERY = 100

class BanditStateManager:
    def __init__(self):
        self.client = redis.Redis(
            host=settings.REDIS_HOST, port=settings.REDIS_PORT, decode_responses=True
        )
        self._n = 0

    def save(self, router: LinUCBRouter):
        self.client.set(REDIS_KEY, router.serialize())
        log.info("state_saved", rounds=router.total_rounds)

    def load(self, router: LinUCBRouter) -> bool:
        raw = self.client.get(REDIS_KEY)
        if not raw:
            return False
        router.deserialize(raw)
        return True

    def maybe_checkpoint(self, router: LinUCBRouter):
        self._n += 1
        if self._n % CHECKPOINT_EVERY == 0:
            self.save(router)
