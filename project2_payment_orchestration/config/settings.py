from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379

    GATEWAYS: List[str] = ["razorpay", "payu", "stripe", "cashfree"]
    LINUCB_ALPHA: float = 0.5
    CONTEXT_DIM: int = 12

    CB_FAILURE_THRESHOLD: int = 5
    CB_RECOVERY_TIMEOUT: int = 30

    MAX_RETRY_ATTEMPTS: int = 2
    RETRY_BACKOFF_BASE: float = 0.1

    MDR_RATES: dict = {
        "razorpay":  {"upi": 0.0,  "card": 0.020, "netbanking": 0.015},
        "payu":      {"upi": 0.0,  "card": 0.022, "netbanking": 0.016},
        "stripe":    {"upi": 0.0,  "card": 0.025, "netbanking": 0.018},
        "cashfree":  {"upi": 0.0,  "card": 0.019, "netbanking": 0.014},
    }

    API_SECRET_KEY: str = "change-me-in-prod"

    class Config:
        env_file = ".env"

settings = Settings()
