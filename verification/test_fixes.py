from tests.conftest import client, seeded


def checkout(client, key, token="tok"):
    return client.post(
        "/checkout",
        headers={"Idempotency-Key": key},
        json={"customer_id": "alex", "payment_token": token},
    )


def add_item(client):
    return client.post(
        "/cart/alex/items",
        json={"product_id": 1, "quantity": 1},
    )


def test_retry_returns_same_order(seeded):
    add_item(seeded)
    first = checkout(seeded, " Order-ABC ")
    assert first.status_code == 200

    add_item(seeded)
    retry = checkout(seeded, "order-abc")
    assert retry.status_code == 200
    assert retry.json() == first.json()
    assert len(seeded.get("/orders").json()) == 1
    assert seeded.get("/products/1").json()["inventory"] == 19
    assert seeded.get("/cart/alex").json()["items"][0]["quantity"] == 1

    from app.database import SessionLocal
    from app.models import PaymentAttempt

    with SessionLocal() as db:
        assert db.query(PaymentAttempt).count() == 1


def test_blank_key_rejected(seeded):
    add_item(seeded)
    assert checkout(seeded, "   ").status_code == 400
    assert seeded.get("/orders").json() == []
    assert seeded.get("/products/1").json()["inventory"] == 20


def test_configured_decline_token(seeded, monkeypatch):
    from app.config import get_settings
    from app.database import SessionLocal
    from app.models import PaymentAttempt

    monkeypatch.setenv("PAYMENT_DECLINE_TOKEN", "blocked")
    get_settings.cache_clear()

    try:
        add_item(seeded)
        assert checkout(seeded, "payment-1", "blocked").status_code == 402
        assert seeded.get("/orders").json() == []
        assert seeded.get("/products/1").json()["inventory"] == 20
        assert seeded.get("/cart/alex").json()["items"][0]["quantity"] == 1

        with SessionLocal() as db:
            assert db.query(PaymentAttempt).count() == 0

        assert checkout(seeded, "payment-1", "decline").status_code == 200
    finally:
        get_settings.cache_clear()
def test_retry_with_empty_cart(seeded):
    add_item(seeded)
    first = checkout(seeded, " Retry-Empty ")
    assert first.status_code == 200
    assert seeded.get("/cart/alex").json()["items"] == []

    retry = checkout(seeded, "RETRY-EMPTY")
    assert retry.status_code == 200
    assert retry.json() == first.json()
    assert seeded.get("/products/1").json()["inventory"] == 19
    assert len(seeded.get("/orders").json()) == 1


def test_different_keys_create_separate_orders(seeded):
    add_item(seeded)
    first = checkout(seeded, "purchase-1")
    assert first.status_code == 200

    add_item(seeded)
    second = checkout(seeded, "purchase-2")
    assert second.status_code == 200

    assert first.json()["id"] != second.json()["id"]
    assert len(seeded.get("/orders").json()) == 2
    assert seeded.get("/products/1").json()["inventory"] == 18