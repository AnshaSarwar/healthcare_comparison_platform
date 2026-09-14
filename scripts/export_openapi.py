"""Export the FastAPI app's OpenAPI schema to a static JSON file.

Importing backend.main only builds the FastAPI app object (routes + Pydantic
schemas) -- it does not run the app's lifespan, so no DB/Redis/Qdrant
connection is required. Used by `frontend`'s `generate:types` script and by
CI to regenerate frontend/src/lib/generated-types.ts from the same source.
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.main import app  # noqa: E402

OUTPUT_PATH = REPO_ROOT / "openapi.json"


def main() -> None:
    schema = app.openapi()
    OUTPUT_PATH.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote OpenAPI schema to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
