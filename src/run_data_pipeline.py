from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from pipeline_utils import discover_scraper_scripts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run crawler/analysis/frontend pipeline with auto-discovered scrapers"
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Project root directory",
    )
    parser.add_argument(
        "--only",
        nargs="*",
        default=[],
        help="Only run selected scraper site names, e.g. tencent mihoyo",
    )
    parser.add_argument(
        "--skip-crawlers",
        action="store_true",
        help="Skip running crawler scripts",
    )
    parser.add_argument(
        "--skip-analysis",
        action="store_true",
        help="Skip running analysis export",
    )
    parser.add_argument(
        "--skip-frontend-export",
        action="store_true",
        help="Skip running frontend data export",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue with next scraper if one scraper fails",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned commands without execution",
    )
    return parser.parse_args()


def _site_from_script(script: Path) -> str:
    return script.name.replace("_campus_scraper.py", "")


def _run(cmd: list[str], cwd: Path, dry_run: bool = False) -> int:
    pretty = " ".join(cmd)
    print(f"$ {pretty}")
    if dry_run:
        return 0
    completed = subprocess.run(cmd, cwd=str(cwd), check=False)
    return completed.returncode


def run_crawlers(args: argparse.Namespace, root: Path) -> bool:
    src_dir = root / "src"
    scripts = discover_scraper_scripts(src_dir)
    if args.only:
        wanted = set(args.only)
        scripts = [script for script in scripts if _site_from_script(script) in wanted]

    if not scripts:
        print("No scraper scripts selected.")
        return True

    print("Selected crawlers:")
    for script in scripts:
        print(f"  - {_site_from_script(script)}: {script.name}")

    all_ok = True
    for script in scripts:
        rc = _run([sys.executable, str(script)], cwd=root, dry_run=args.dry_run)
        if rc != 0:
            all_ok = False
            print(f"[failed] {_site_from_script(script)} exit_code={rc}")
            if not args.continue_on_error:
                return False
    return all_ok


def run_analysis(args: argparse.Namespace, root: Path) -> bool:
    rc = _run(
        [
            sys.executable,
            str(root / "src" / "run_analysis.py"),
            "--data-dir",
            "data",
            "--output-dir",
            "data/analysis",
        ],
        cwd=root,
        dry_run=args.dry_run,
    )
    return rc == 0


def run_frontend_export(args: argparse.Namespace, root: Path) -> bool:
    rc = _run(
        [sys.executable, str(root / "src" / "export_frontend_jobs.py")],
        cwd=root,
        dry_run=args.dry_run,
    )
    return rc == 0


def main() -> None:
    args = parse_args()
    root = args.root.resolve()

    print(f"Pipeline root: {root}")

    ok = True

    if not args.skip_crawlers:
        ok = run_crawlers(args, root) and ok

    if not args.skip_analysis:
        analysis_ok = run_analysis(args, root)
        ok = analysis_ok and ok
        if not analysis_ok and not args.continue_on_error:
            raise SystemExit(1)

    if not args.skip_frontend_export:
        frontend_ok = run_frontend_export(args, root)
        ok = frontend_ok and ok
        if not frontend_ok and not args.continue_on_error:
            raise SystemExit(1)

    if not ok:
        raise SystemExit(1)

    print("Pipeline done.")


if __name__ == "__main__":
    main()
