"""Writes the API schema to a file; the frontend generates its types from it."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from where_to_go.api import create_app

schema = create_app(lambda: None).openapi()
Path(sys.argv[1]).write_text(json.dumps(schema, ensure_ascii=False, indent=1) + "\n")
