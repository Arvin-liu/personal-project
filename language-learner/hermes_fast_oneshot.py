#!/usr/bin/env python3
"""Run a single Language Learner AI request through the user's local Hermes setup."""

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
    if args.service_tier not in {"priority", "normal"}:
        print("Language Learner Hermes adapter: service tier must be priority or normal", file=sys.stderr)
        return 2
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", args.profile):
        print("Language Learner Hermes adapter: invalid profile name", file=sys.stderr)
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
        if configured_tier != "priority":
            print(
                "Language Learner Hermes adapter: the selected profile must retain "
                "agent.service_tier set to priority",
                file=sys.stderr,
            )
            return 2

        fast_overrides = None
        if args.service_tier == "priority":
            fast_overrides = resolve_fast_mode_overrides(
                args.model, provider=args.provider
            )
            if not fast_overrides or fast_overrides.get("service_tier") != "priority":
                print(
                    f"Language Learner Hermes adapter: Fast tier is unsupported for {args.provider}/{args.model}",
                    file=sys.stderr,
                )
                return 2

        import run_agent

        original_init = run_agent.AIAgent.__init__

        def reader_init(self, *init_args, **kwargs):
            request_overrides = dict(kwargs.get("request_overrides") or {})
            if fast_overrides is not None:
                request_overrides.update(fast_overrides)
                kwargs["service_tier"] = "priority"
            else:
                # The isolated profile defaults to Fast for dictionary lookup.
                # Structure analysis explicitly removes that request-level tier.
                request_overrides.pop("service_tier", None)
                request_overrides.pop("speed", None)
                extra_body = request_overrides.get("extra_body")
                if isinstance(extra_body, dict):
                    extra_body.pop("service_tier", None)
                    extra_body.pop("speed", None)
                    if not extra_body:
                        request_overrides.pop("extra_body", None)
                kwargs["service_tier"] = None
            kwargs["request_overrides"] = request_overrides or None
            kwargs["enabled_toolsets"] = []
            kwargs["skip_context_files"] = True
            kwargs["skip_memory"] = True
            kwargs["skip_background_review"] = True
            original_init(self, *init_args, **kwargs)

        run_agent.AIAgent.__init__ = reader_init
        from hermes_cli.oneshot import run_oneshot

        prompt = sys.stdin.read()
        if not prompt.strip():
            print("Language Learner Hermes adapter: empty prompt", file=sys.stderr)
            return 2
        return run_oneshot(
            prompt,
            model=args.model,
            provider=args.provider,
            reasoning=args.reasoning,
        )
    except Exception as exc:
        print(f"Language Learner Hermes adapter: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
