from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.evaluation import evaluation_service  # noqa: E402


async def main() -> None:
    report = await evaluation_service.run()
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"report: {Path('reports/evaluation-latest.json').resolve()}")


if __name__ == "__main__":
    asyncio.run(main())
