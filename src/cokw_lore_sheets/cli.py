"""Command line interface; compare and check work without Google dependencies."""
from pathlib import Path
import argparse
import json
import sys
import uuid

from .config import validate
from .model import capture, validate_snapshot, utc_now
from .compare import compare, compatible
from .checks import evaluate
from .storage import data_dir, load_json, write_json


def emit(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def parser():
    p = argparse.ArgumentParser(description="Read-only Google Sheets audit snapshots and comparisons")
    p.add_argument("--version", action="version", version="0.1.0")
    sub = p.add_subparsers(dest="command", required=True)
    auth = sub.add_parser("auth", help="Authorize read-only access in a browser")
    auth.add_argument("--client-secrets", required=True, type=Path)
    auth.add_argument("--token", type=Path, default=data_dir() / "token.json")
    dump = sub.add_parser("dump", help="Capture all selected sheets and run configured checks")
    dump.add_argument("--config", required=True, type=Path)
    dump.add_argument("--output", type=Path)
    dump.add_argument("--baseline", type=Path, help="Previous complete snapshot for unchanged checks")
    dump.add_argument("--token", type=Path, default=data_dir() / "token.json")
    dump.add_argument("--fixture", type=Path, help="Use a synthetic offline source instead of Google")
    check = sub.add_parser("check", help="Run checks on an existing snapshot, offline")
    check.add_argument("snapshot", type=Path)
    check.add_argument("--config", required=True, type=Path)
    check.add_argument("--baseline", type=Path)
    check.add_argument("--output", type=Path)
    diff = sub.add_parser("compare", help="Compare two complete snapshots, offline")
    diff.add_argument("before", type=Path)
    diff.add_argument("after", type=Path)
    diff.add_argument("--results", action="store_true", help="Include per-cell calculated result changes")
    diff.add_argument("--output", type=Path)
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "auth":
            from .google import authorize
            authorize(args.client_secrets, args.token)
            print(f"Read-only authorization saved to {args.token}")
            return 0
        if args.command == "compare":
            report = compare(load_json(args.before), load_json(args.after), args.results)
            if args.output:
                write_json(args.output, report)
            emit(report)
            return 1 if report["has_changes"] else 0
        config = validate(load_json(args.config))
        baseline = validate_snapshot(load_json(args.baseline)) if args.baseline else None
        if any(r["test"] == "unchanged" for r in config["checks"]) and baseline is None:
            raise ValueError("An unchanged check requires --baseline")
        if args.command == "dump":
            if args.fixture:
                from .fixture import FixtureProvider
                provider = FixtureProvider(args.fixture)
            else:
                from .google import GoogleProvider
                provider = GoogleProvider(args.token)
            snapshot = capture(provider, config)
            if baseline:
                # An incomplete dump is still saved with its errors, without claiming removals.
                if snapshot["complete"]:
                    compatible(baseline, snapshot)
            snapshot["checks"] = evaluate(snapshot, config, baseline)
            date = utc_now().replace(":", "").replace("+", "_")
            output = args.output or data_dir() / "snapshots" / (date+"-"+uuid.uuid4().hex[:8]+".snapshot.json")
            write_json(output, snapshot)
            emit({"output": str(output), "complete": snapshot["complete"],
                  "files": len(snapshot["files"]), "errors": snapshot["errors"],
                  "checks": snapshot["checks"]})
            if not snapshot["complete"]:
                return 2
            return 0 if snapshot["checks"]["passed"] else 1
        snapshot = validate_snapshot(load_json(args.snapshot))
        if snapshot["selection"] != config["files"] or snapshot["include_results"] != config["include_results"]:
            raise ValueError("Config capture selection differs from the snapshot")
        if baseline:
            compatible(baseline, snapshot)
        report = evaluate(snapshot, config, baseline)
        if args.output:
            write_json(args.output, report)
        emit(report)
        return 0 if report["passed"] else 1
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        # Do not print third-party credential objects or request URLs.
        status = getattr(getattr(exc, "resp", None), "status", None)
        print(f"Google request failed ({type(exc).__name__}, HTTP {status}). "
              "Check authentication, API access and connectivity.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
