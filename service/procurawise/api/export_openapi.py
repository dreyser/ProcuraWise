import json
from pathlib import Path

from procurawise.api.main import app

OUTPUT_PATH = Path(__file__).resolve().parents[3] / "apps" / "web" / "openapi.json"


def main() -> None:
    OUTPUT_PATH.write_text(json.dumps(app.openapi(), indent=2))
    print(f"wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
