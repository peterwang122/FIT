from app.services.quant_service import QuantService


def test_quant_service_initializes_dependencies():
    db = object()

    service = QuantService(db)

    assert service.db is db
    assert service.stock_service.db is db
    assert service.notification_service.db is db
