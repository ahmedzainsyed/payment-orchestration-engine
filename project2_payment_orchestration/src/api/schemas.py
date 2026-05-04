from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum

class PaymentMethod(str, Enum):
    upi = "upi"; card = "card"; netbanking = "netbanking"

class Bank(str, Enum):
    hdfc="hdfc"; icici="icici"; sbi="sbi"; axis="axis"; kotak="kotak"; other="other"

class PaymentRequest(BaseModel):
    transaction_id: str = Field(..., min_length=8)
    amount: float = Field(..., gt=0, le=10_000_000)
    currency: str = Field(default="INR", pattern="^[A-Z]{3}$")
    payment_method: PaymentMethod = PaymentMethod.upi
    bank: Bank = Bank.hdfc
    merchant_id: str
    hour: Optional[int] = Field(default=None, ge=0, le=23)
    region: Optional[str] = None

class AttemptDetail(BaseModel):
    attempt: int; gateway: str; success: bool
    latency_ms: float; error_code: str; cost_inr: float

class PaymentResponse(BaseModel):
    transaction_id: str; final_status: str; attempts: int
    history: List[AttemptDetail]; total_latency_ms: float
    gateway_scores: dict; bandit_rounds: int
