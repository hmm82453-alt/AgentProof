from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path


TEST_DB = Path(tempfile.gettempdir()) / f"delta-agent-tests-{uuid.uuid4().hex}.db"
os.environ["DATABASE_PATH"] = str(TEST_DB)
# Unit and integration tests must never call a paid model endpoint.
os.environ["LLM_API_KEY"] = ""
