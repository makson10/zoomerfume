"""Write the API's OpenAPI schema to ``openapi.json``. Needs no services and no secrets.

    python -m app.api.openapi

The web chat's API types are generated from this file (``npm run api:types`` in
``frontend/``), so run both after changing a route or one of its models.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.core.config import Settings
from app.main import create_app

SCHEMA_PATH = Path("openapi.json")


def main() -> None:
    # The schema doesn't depend on the settings, so placeholders are enough.
    settings = Settings(_env_file=None, openai_api_key="unused", session_secret="unused" * 6)
    schema = create_app(settings).openapi()
    SCHEMA_PATH.write_text(json.dumps(schema, indent=2, ensure_ascii=False) + "\n")
    print(
        f"Wrote {SCHEMA_PATH}: {len(schema['paths'])} paths, "
        f"{len(schema['components']['schemas'])} schemas"
    )


if __name__ == "__main__":
    main()
