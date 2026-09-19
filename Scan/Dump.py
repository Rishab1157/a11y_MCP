import json
from pathlib import Path

DUMP_DIR = Path(__file__).parent 
def dump_json(data, filename: str) -> None:
    """Dump data as-is, overwriting the previous run. Debug aid — delete later."""
    with open(DUMP_DIR / filename, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)