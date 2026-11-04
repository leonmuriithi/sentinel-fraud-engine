"""Send demo transactions to the running ingestor (standard library only).

    python scripts/send_test_transactions.py
"""
import json
import urllib.request

URL = "http://localhost:3000/api/v1/transaction"


def send(label, **overrides):
    payload = {"userId": "user_123", "amount": 1500, "currency": "KES",
               "location": "Nairobi", "merchantId": "M_88291", **overrides}
    req = urllib.request.Request(URL, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            print(f"{label:<34} -> {resp.status} {resp.read().decode()}")
    except Exception as exc:  # noqa: BLE001
        print(f"{label:<34} -> FAILED: {exc}")


if __name__ == "__main__":
    send("1. ordinary purchase (clean)")
    send("2. amount above ceiling", userId="user_456", amount=5_000_000)
    for i in range(9):
        send(f"3. velocity burst #{i + 1}", userId="user_789", amount=800)
    send("4. large amount + location jump", userId="user_321", amount=1500)
    send("   ...same user, 20s later, Lagos", userId="user_321", amount=60_000, location="Lagos")
    send("5. invalid payload (goes nowhere)", amount=-10)
    print("\nWatch the detector:  docker compose logs -f detector")
    print("Read the alerts:     docker compose exec kafka kafka-console-consumer "
          "--bootstrap-server kafka:29092 --topic fraud-alerts --from-beginning")
