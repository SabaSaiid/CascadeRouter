import copy
import json
import pytest
from scripts.source_inventory import MANIFEST, allowed, valid_entries, verify


def test_actual_manifest_matches_committed_sources_without_claiming_a_build():
    result = verify(json.loads(MANIFEST.read_text(encoding="utf-8")))
    assert result["source_inventory_verified"] and result["artifacts"] > 0
    assert result["production_build_verified"] is False


@pytest.mark.parametrize("path", ["../private.py", "/etc/private.py", "C:/private.py", "backend/.env", "tests/fixtures/sample_repo/app.py", "backend/../private.py"])
def test_inventory_cannot_name_target_fixtures_or_private_host_inputs(path):
    assert not allowed(path)


@pytest.mark.parametrize("defect", ["duplicate", "hash", "size", "path"])
def test_invalid_inventory_metadata_cannot_verify(defect):
    entries = [dict(path="backend/main.py", bytes=10, sha256="a" * 64)]
    if defect == "duplicate": entries.append(copy.deepcopy(entries[0]))
    if defect == "hash": entries[0]["sha256"] = "unknown"
    if defect == "size": entries[0]["bytes"] = True
    if defect == "path": entries[0]["path"] = "../private.py"
    assert not valid_entries(entries)


def test_well_formed_but_wrong_digest_is_rejected_against_actual_git_blobs():
    value = json.loads(MANIFEST.read_text(encoding="utf-8"))
    value["artifacts"][0]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="source_inventory_mismatch"):
        verify(value)
