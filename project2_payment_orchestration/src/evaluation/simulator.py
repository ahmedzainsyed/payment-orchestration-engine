"""
Evaluation harness — A/B test AI routing vs round-robin baseline.
Run: python -m src.evaluation.simulator --n 2000
"""
import asyncio, random, argparse, time
from typing import Dict

BANKS   = ["hdfc", "icici", "sbi", "axis", "kotak"]
METHODS = ["upi", "card", "netbanking"]
AMOUNTS = [500, 1000, 2500, 5000, 15_000, 50_000, 100_000]

def make_txn(i: int) -> dict:
    return {
        "transaction_id": f"TXN{i:010d}",
        "amount":         random.choice(AMOUNTS),
        "payment_method": random.choice(METHODS),
        "bank":           random.choice(BANKS),
        "merchant_id":    f"MCH{random.randint(1,50):03d}",
        "hour":           random.randint(0, 23),
    }

async def run_ai(n: int) -> Dict:
    from src.routing.router import PaymentOrchestrator
    orch = PaymentOrchestrator()
    ok, fail, retries, cost = 0, 0, 0, 0.0
    start = time.time()
    for i in range(n):
        result = await orch.process(make_txn(i))
        if result["final_status"] == "success":
            ok += 1
            cost += sum(h["cost_inr"] for h in result["history"])
        else:
            fail += 1
        retries += result["attempts"] - 1
        if (i+1) % 500 == 0:
            print(f"  [{i+1}/{n}] success_rate={ok/(i+1):.2%}")
    elapsed = time.time() - start
    return {"success": ok, "failed": fail, "retries": retries,
            "avg_cost": cost/max(ok,1), "tps": n/elapsed,
            "gateway_scores": orch.router.q_values()}

async def run_baseline(n: int) -> Dict:
    """Round-robin baseline — no AI."""
    from src.gateway.mock_gateways import gateway_simulator
    from config.settings import settings
    ok, fail, retries = 0, 0, 0
    gateways = settings.GATEWAYS
    for i in range(n):
        txn = make_txn(i)
        gw  = gateways[i % len(gateways)]
        resp = await gateway_simulator.call(
            gw, txn["payment_method"], txn["bank"],
            txn["amount"], txn["hour"]
        )
        if resp.success:
            ok += 1
        else:
            # one retry on next gateway
            gw2  = gateways[(i+1) % len(gateways)]
            resp2 = await gateway_simulator.call(
                gw2, txn["payment_method"], txn["bank"],
                txn["amount"], txn["hour"]
            )
            retries += 1
            if resp2.success: ok += 1
            else: fail += 1
    return {"success": ok, "failed": fail, "retries": retries}

async def main(n: int):
    print(f"\n{'='*55}")
    print(f"  EVALUATION: {n} transactions")
    print(f"{'='*55}")

    print("\n⚡ Running Round-Robin Baseline ...")
    baseline = await run_baseline(n)
    base_sr  = baseline["success"] / n

    print("\n🤖 Running LinUCB AI Routing ...")
    ai = await run_ai(n)
    ai_sr = ai["success"] / n

    print(f"\n{'='*55}")
    print(f"  RESULTS")
    print(f"{'='*55}")
    print(f"  Baseline success rate : {base_sr:.2%}")
    print(f"  AI routing success    : {ai_sr:.2%}")
    print(f"  Improvement           : +{(ai_sr - base_sr)*100:.1f}%")
    print(f"  AI retries            : {ai['retries']}")
    print(f"  Baseline retries      : {baseline['retries']}")
    print(f"  Avg cost per txn      : ₹{ai['avg_cost']:.2f}")
    print(f"  Throughput            : {ai['tps']:.1f} txn/s")
    print(f"  Gateway scores        : {ai['gateway_scores']}")
    print(f"{'='*55}\n")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=2000)
    args = ap.parse_args()
    asyncio.run(main(args.n))
