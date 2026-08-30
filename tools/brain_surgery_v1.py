from pathlib import Path
import re

ROOT = Path("production_v2")
BRAINS = [f"e{i}_brain.py" for i in range(1, 10)]

TEMPLATE = '''\n\n# === BRAIN_SURGERY_V1 ===\nfrom .professional_reasoning import apply_professional_layer as _apply_professional_layer\n\n_ORIGINAL_{name} = {name}\n\ndef {name}(snapshot):\n    """Professional reasoning wrapper; original brain remains the domain specialist."""\n    result = _ORIGINAL_{name}(snapshot)\n    return _apply_professional_layer(result, "{brain}")\n'''

for filename in BRAINS:
    path = ROOT / filename
    text = path.read_text(encoding="utf-8")
    if "# === BRAIN_SURGERY_V1 ===" in text:
        continue
    name = f"analyze_e{filename[1]}"
    if not re.search(rf"^def {name}\s*\(", text, re.M):
        raise SystemExit(f"missing {name} in {filename}")
    # Keep the original implementation byte-for-byte and wrap its public entry point.
    text = re.sub(rf"^def {name}\s*\(", f"def _original_{name}(", text, count=1, flags=re.M)
    text += TEMPLATE.format(name=name, brain=f"E{filename[1]}").replace(f"_ORIGINAL_{name} = {name}", f"_ORIGINAL_{name} = _original_{name}")
    path.write_text(text, encoding="utf-8")
print("patched", ", ".join(BRAINS))
