"""Manual Garmin token bootstrap entrypoint."""

from __future__ import annotations

import json
import logging

from garmin_client import bootstrap_garmin_tokens


logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger(__name__)


def main() -> None:
    """Run the interactive Garmin bootstrap flow and print verification metadata.

    Returns:
        None
    """
    result = bootstrap_garmin_tokens()
    LOGGER.info("Garmin bootstrap completed successfully.")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
