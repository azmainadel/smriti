"""Write the OpenAPI schema the web app and extension generate their types from."""

import json
import sys
from pathlib import Path

from smriti.main import app

out = Path(sys.argv[1] if len(sys.argv) > 1 else "../web/src/lib/openapi.json")
out.write_text(json.dumps(app.openapi(), indent=2) + "\n")
print(f"wrote {out}")
