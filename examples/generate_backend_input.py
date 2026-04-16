#!/usr/bin/env python3
"""Generate Backend input data from the copied OASIS Reddit dataset."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.frontend_settings import DEBUG_RUN_DEFAULTS
from data.oasis_reddit.oasis_adapter import build_payload


ROOT = PROJECT_ROOT


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agents", type=int, default=DEBUG_RUN_DEFAULTS.num_agents)
    parser.add_argument("--rounds", type=int, default=DEBUG_RUN_DEFAULTS.rounds)
    parser.add_argument("--seed-posts", type=int, default=DEBUG_RUN_DEFAULTS.seed_posts)
    parser.add_argument("--seed", type=int, default=DEBUG_RUN_DEFAULTS.seed)
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=ROOT / "examples" / "backend_sample_input.json",
    )
    args = parser.parse_args()

    payload = build_payload(
        num_agents=args.agents,
        rounds=args.rounds,
        seed_posts=args.seed_posts,
        seed=args.seed,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"Wrote {args.output} from copied OASIS Reddit data "
        f"(agents={payload['meta']['num_agents']}, rounds={args.rounds}, seed_posts={payload['meta']['seed_posts']})",
        flush=True,
    )


if __name__ == "__main__":
    main()
