"""Write the OpenAPI document of the app to openapi.json (same as GET /openapi.json)."""

import json
from pathlib import Path

from main import app

Path("openapi.json").write_text(json.dumps(app.openapi(), indent=2) + "\n", encoding="utf-8")
print("openapi.json written")
