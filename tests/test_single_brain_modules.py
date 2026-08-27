from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "production_v2"


def test_e1_to_e5_have_stable_single_brain_entrypoints():
    for engine in range(1, 6):
        path = ROOT / f"e{engine}_brain.py"
        assert path.exists(), f"missing E{engine} brain"
        text = path.read_text(encoding="utf-8")
        assert f"e{engine}_brain_v" not in text
        assert "from .e4_brain_v14" not in text


def test_e3_is_not_a_wrapper():
    text = (ROOT / "e3_brain.py").read_text(encoding="utf-8")
    assert "from .e3_brain_v8" not in text
    assert "from . import e3_brain_v6" not in text


def test_e4_is_not_a_wrapper():
    text = (ROOT / "e4_brain.py").read_text(encoding="utf-8")
    assert "from .e4_brain_v14" not in text
