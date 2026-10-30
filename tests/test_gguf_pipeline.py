from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_pipeline_ist_fail_closed_und_quantisiert_beide_kandidaten():
    text = (ROOT / "training/gguf_pipeline.sh").read_text(encoding="utf-8")
    smoke = text.index('gguf_smoke_api.sh')
    q5 = text.index('"$QUANTIZE" "$BASIS" "$Q5" Q5_K_M')
    q4 = text.index('"$QUANTIZE" "$BASIS" "$Q4" Q4_K_M')
    assert "set -euo pipefail" in text
    assert "--no-mtp --no-lazy" in text
    assert smoke < q5 < q4
    assert text.count("gguf_smoke_api.sh") >= 2
    assert 'for datei in "$Q5" "$Q4"' in text


def test_gguf_export_deaktiviert_qwen_mtp_block():
    text = (ROOT / "training/gguf_pipeline.sh").read_text(encoding="utf-8")
    assert "BF16-no-mtp.gguf" in text
    assert "--no-mtp --no-lazy" in text
