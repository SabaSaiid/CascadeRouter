"""Prevent frontend types/response validators drifting from the actual backend."""

from frontend.scripts.sync_contracts import ROOT, render_contract


def test_frontend_contract_matches_current_openapi():
    assert (ROOT / "frontend/src/services/contracts.ts").read_text(encoding="utf-8") == render_contract()
