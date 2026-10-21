"""Deployment must preserve unrelated settings and reject unverified candidates."""
import json
from pathlib import Path

import pytest

from deploy_model import configured_text, verify_metadata


def test_model_configuration_preserves_unrelated_values():
    original = '# local settings\nLLM_API_KEY="keep-this-literal"\nMODEL_MANIFEST="old"\nPORT=8000\n'
    updated, previous = configured_text(original, Path("E:/AgriScan/models/new/manifest.json"))
    assert 'LLM_API_KEY="keep-this-literal"\n' in updated
    assert "# local settings\n" in updated and "PORT=8000\n" in updated
    assert updated.count("MODEL_MANIFEST=") == 1
    assert previous == ['MODEL_MANIFEST="old"']
    assert updated.endswith('MODEL_MANIFEST="E:/AgriScan/models/new/manifest.json"\n')


def test_duplicate_keys_are_replaced_and_missing_newline_is_handled():
    updated, previous = configured_text("MODEL_MANIFEST=old\nexport MODEL_MANIFEST=other\nKEEP=1", Path("model.json"))
    assert previous == ["MODEL_MANIFEST=old", "export MODEL_MANIFEST=other"]
    assert updated == 'KEEP=1\nMODEL_MANIFEST="model.json"\n'


@pytest.mark.parametrize("metadata", [
    {"task": "classify", "validation_passed": False},
    {"task": "detect", "validation_passed": True},
    {"task": "classify", "validation_passed": True, "validation_top1": 0.5,
     "validation_macro_f1": 0.9, "onnx_max_abs_error": 0.0},
    {"task": "classify", "validation_passed": True, "validation_top1": 0.99,
     "validation_macro_f1": 0.99, "onnx_max_abs_error": 0.01},
])
def test_failed_quality_and_export_gates_refuse_deployment(tmp_path, metadata):
    (tmp_path / "manifest.json").write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(ValueError):
        verify_metadata(tmp_path)
