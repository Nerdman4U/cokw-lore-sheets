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
    p = argparse.ArgumentParser(description="Google Sheets audits and explicit schema-driven TMP regeneration")
    p.add_argument("--version", action="version", version="0.1.0")
    sub = p.add_subparsers(dest="command", required=True)
    auth = sub.add_parser("auth", help="Authorize read-only access in a browser")
    auth.add_argument("--client-secrets", required=True, type=Path)
    auth.add_argument("--token", type=Path, default=data_dir() / "token.json")
    dump = sub.add_parser("dump", help="Capture all selected sheets and run configured checks")
    dump.add_argument("--config", required=True, type=Path)
    dump.add_argument("--output", type=Path)
    dump.add_argument("--baseline", type=Path, help="Previous complete snapshot for unchanged checks")
    dump.add_argument("--transport", choices=("webapp", "oauth"), default="webapp")
    dump.add_argument("--web-app-url", help="Defaults to LORE_SHEETS_WEB_APP_URL")
    dump.add_argument("--token", type=Path, default=data_dir() / "token.json")
    dump.add_argument("--fixture", type=Path, help="Use a synthetic offline source instead of Google")
    check = sub.add_parser("check", help="Run checks on an existing snapshot, offline")
    check.add_argument("snapshot", type=Path)
    check.add_argument("--config", required=True, type=Path)
    check.add_argument("--baseline", type=Path)
    check.add_argument("--output", type=Path)
    check.add_argument("--format", choices=("json", "summary"), default="json")
    listing = sub.add_parser("list", help="List cells targeted by configured checks, offline")
    listing.add_argument("snapshot", type=Path)
    listing.add_argument("--config", required=True, type=Path)
    listing.add_argument("--format", choices=("tsv", "json"), default="tsv")
    listing.add_argument("--output", type=Path)
    diff = sub.add_parser("compare", help="Compare two complete snapshots, offline")
    diff.add_argument("before", type=Path)
    diff.add_argument("after", type=Path)
    diff.add_argument("--config", type=Path, help="Optional anomaly thresholds")
    diff.add_argument("--results", action="store_true", help="Include per-cell calculated result changes")
    diff.add_argument("--output", type=Path)
    regen = sub.add_parser("regenerate", help="Regenerate assigned TMP sheets, preserving keyed inputs")
    regen.add_argument("file_id", help="Registered spreadsheet ID")
    regen.add_argument("sheet_name", nargs="?", help="One assigned TMP_ sheet; default: all assigned schemas")
    regen.add_argument("--dry-run", action="store_true", help="Read and validate the plan without writing")
    regen.add_argument("--web-app-url", help="Defaults to LORE_SHEETS_WEB_APP_URL")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "regenerate":
            from .regeneration import regenerate
            report = regenerate(args.file_id, args.sheet_name, web_app_url=args.web_app_url, dry_run=args.dry_run)
            emit(report)
            return 0 if report["status"] in ("regenerated", "planned") else 1
        if args.command == "auth":
            from .google import authorize
            authorize(args.client_secrets, args.token)
            print(f"Read-only authorization saved to {args.token}")
            return 0
        if args.command == "compare":
            report = compare(load_json(args.before), load_json(args.after), args.results,
                             validate(load_json(args.config)) if args.config else None)
            if args.output:
                write_json(args.output, report)
            emit(report)
            return 1 if report["has_changes"] or report["sheet_audit"]["warnings"] else 0
        config = validate(load_json(args.config))
        if args.command == "list":
            from .listing import list_cells, render
            from .storage import write_text
            snapshot = validate_snapshot(load_json(args.snapshot), complete=False)
            report = list_cells(snapshot, config)
            text = render(report, args.format)
            if args.output:
                write_text(args.output, text)
            else:
                sys.stdout.write(text)
            for issue in report["issues"]:
                print("Listing issue: " + json.dumps(issue, ensure_ascii=False), file=sys.stderr)
            if not report["source_complete"]:
                return 2
            return 1 if report["issues"] else 0
        baseline = validate_snapshot(load_json(args.baseline)) if args.baseline else None
        if any(r["test"] == "unchanged" for r in config["checks"]) and baseline is None:
            raise ValueError("An unchanged check requires --baseline")
        if args.command == "dump":
            if args.fixture:
                from .fixture import FixtureProvider
                provider = FixtureProvider(args.fixture)
            elif args.transport == "webapp":
                from .webapp import WebAppProvider
                provider = WebAppProvider(args.web_app_url)
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
        if snapshot["include_results"] != config["include_results"]:
            raise ValueError("Config include_results differs from the snapshot")
        if baseline:
            compatible(baseline, snapshot)
        report = evaluate(snapshot, config, baseline)
        if args.format == "summary":
            from .checks import summary_lines
            from .storage import write_text
            text = "\n".join(summary_lines(snapshot, config, report)) + "\n"
            if args.output:
                write_text(args.output, text)
            else:
                sys.stdout.write(text)
            return 0 if report["passed"] and config["checks"] else 1
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
