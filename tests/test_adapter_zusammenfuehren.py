from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_merge_skript_verwendet_unquantisierte_bf16_basis_und_sicheren_merge():
    text = (ROOT / "training" / "adapter_zusammenfuehren.py").read_text(encoding="utf-8")
    assert "BitsAndBytesConfig" not in text
    assert "dtype=torch.bfloat16" in text
    assert "merge_and_unload(safe_merge=True)" in text
    assert "local_files_only=True" in text


def test_merge_skript_ueberschreibt_keinen_vollen_ausgabeordner():
    text = (ROOT / "training" / "adapter_zusammenfuehren.py").read_text(encoding="utf-8")
    assert "Ausgabeordner ist nicht leer" in text
