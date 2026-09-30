#!/usr/bin/env python3
"""Run one Hermes request with the English Reader's isolated Fast Codex route."""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--reasoning", required=True)
    parser.add_argument("--service-tier", required=True)
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", args.profile):
        print("Hermes Fast runner: invalid profile name", file=sys.stderr)
        return 2

    profile_dir = Path.home() / ".hermes" / "profiles" / args.profile
    if not (profile_dir / "config.yaml").is_file():
        print(f"Hermes Fast runner: profile config not found: {profile_dir}", file=sys.stderr)
        return 2
    os.environ["HERMES_HOME"] = str(profile_dir)
    os.environ["HERMES_IGNORE_RULES"] = "1"

    agent_root = Path(
        os.environ.get("HERMES_AGENT_ROOT", str(Path.home() / ".hermes/hermes-agent"))
    ).expanduser()
    if not (agent_root / "run_agent.py").is_file():
        print(f"Hermes Fast runner: Hermes source not found: {agent_root}", file=sys.stderr)
        return 2
    sys.path.insert(0, str(agent_root))

    try:
        from hermes_cli.config import load_config
        from hermes_cli.cli_config_load import _parse_service_tier_config
        from hermes_cli.models import resolve_fast_mode_overrides

        config = load_config()
        configured_tier = _parse_service_tier_config(
            (config.get("agent") or {}).get("service_tier", "")
        )
        if configured_tier != args.service_tier:
            print(
                "Hermes Fast runner: the reader profile must have agent.service_tier set to "
                f"{args.service_tier}",
                file=sys.stderr,
            )
            return 2

        fast_overrides = resolve_fast_mode_overrides(
            args.model, provider=args.provider
        )
        if not fast_overrides or fast_overrides.get("service_tier") != args.service_tier:
            print(
                f"Hermes Fast runner: Fast tier is unsupported for {args.provider}/{args.model}",
                file=sys.stderr,
            )
            return 2

        import run_agent

        original_init = run_agent.AIAgent.__init__

        def fast_init(self, *init_args, **kwargs):
            request_overrides = dict(kwargs.get("request_overrides") or {})
            request_overrides.update(fast_overrides)
            kwargs["request_overrides"] = request_overrides
            kwargs["service_tier"] = args.service_tier
            kwargs["enabled_toolsets"] = []
            kwargs["skip_context_files"] = True
            kwargs["skip_memory"] = True
            kwargs["skip_background_review"] = True
            original_init(self, *init_args, **kwargs)

        run_agent.AIAgent.__init__ = fast_init
        from hermes_cli.oneshot import run_oneshot

        prompt = sys.stdin.read()
        if not prompt.strip():
            print("Hermes Fast runner: empty prompt", file=sys.stderr)
            return 2
        return run_oneshot(
            prompt,
            model=args.model,
            provider=args.provider,
            reasoning=args.reasoning,
        )
    except Exception as exc:
        print(f"Hermes Fast runner: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
