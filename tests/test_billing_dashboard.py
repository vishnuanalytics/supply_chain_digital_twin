"""ui/tabs/billing.py's _recommended_action(): a computed (not LLM-generated) next-step
recommendation for the shipment detail dialog, checked in a deliberate priority order so
the single icon+message shown is always the most urgent, decision-relevant fact."""
from datetime import date

from ui.tabs.billing import _recommended_action

TODAY = date(2026, 9, 21)


def _detail(**overrides):
    base = {
        "status": "delivered",
        "penalty_clause": False,
        "delay_reason": None,
        "carrier": "Schneider National",
        "account_manager": "Sarah Chen",
        "invoice_status": "paid",
        "invoice_amount": None,
        "contract_end_date": date(2027, 1, 1),
        "auto_renew": True,
    }
    base.update(overrides)
    return base


class TestRecommendedAction:
    def test_delayed_with_penalty_clause_is_top_priority(self):
        detail = _detail(status="delayed", penalty_clause=True, invoice_status="overdue")
        icon, message = _recommended_action(detail, TODAY)
        assert icon == "🔴"
        assert "Penalty clause applies" in message
        assert "Sarah Chen" in message

    def test_delayed_without_penalty_names_the_carrier(self):
        detail = _detail(status="delayed", delay_reason="Port congestion", carrier="XPO Logistics")
        icon, message = _recommended_action(detail, TODAY)
        assert icon == "🟡"
        assert "Port congestion" in message
        assert "XPO Logistics" in message

    def test_overdue_invoice_flagged_when_shipment_itself_is_fine(self):
        detail = _detail(status="delivered", invoice_status="overdue", invoice_amount=42500.5)
        icon, message = _recommended_action(detail, TODAY)
        assert icon == "🔴"
        assert "overdue" in message
        assert "$42,500.50" in message

    def test_contract_expiring_within_red_threshold_without_auto_renew(self):
        detail = _detail(auto_renew=False, contract_end_date=date(2026, 9, 30))
        icon, message = _recommended_action(detail, TODAY)
        assert icon == "🔴"
        assert "9 day(s)" in message
        assert "does not auto-renew" in message

    def test_contract_expiring_within_yellow_threshold_without_auto_renew(self):
        detail = _detail(auto_renew=False, contract_end_date=date(2026, 11, 1))
        icon, message = _recommended_action(detail, TODAY)
        assert icon == "🟡"
        assert "does not auto-renew" in message

    def test_expiring_soon_but_auto_renews_is_not_flagged(self):
        detail = _detail(auto_renew=True, contract_end_date=date(2026, 9, 30))
        icon, message = _recommended_action(detail, TODAY)
        assert icon == "🟢"
        assert "On track" in message

    def test_all_clear_when_delivered_paid_and_far_from_expiry(self):
        detail = _detail()
        icon, message = _recommended_action(detail, TODAY)
        assert icon == "🟢"
        assert "On track" in message

    def test_penalty_clause_outranks_overdue_invoice(self):
        detail = _detail(status="delayed", penalty_clause=True, invoice_status="overdue", invoice_amount=100.0)
        icon, message = _recommended_action(detail, TODAY)
        assert "Penalty clause applies" in message

    def test_overdue_invoice_outranks_upcoming_non_auto_renewing_expiry(self):
        detail = _detail(invoice_status="overdue", invoice_amount=9.99, auto_renew=False, contract_end_date=date(2026, 9, 25))
        icon, message = _recommended_action(detail, TODAY)
        assert "overdue" in message
