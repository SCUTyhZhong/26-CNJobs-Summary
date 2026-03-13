from __future__ import annotations

import argparse
import json
from pathlib import Path

from analysis_api import get_analysis_payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run job data analysis")
    parser.add_argument("--data-dir", default="data", help="Input data directory")
    parser.add_argument(
        "--output-dir",
        default="data/analysis",
        help="Output directory for analysis artifacts",
    )
    parser.add_argument("--top-n", type=int, default=15, help="Top N for ranking lists")
    parser.add_argument(
        "--advanced",
        action="store_true",
        help="Enable deeper ML/NLP analysis (clustering, topics, embeddings)",
    )
    parser.add_argument("--clusters", type=int, default=8, help="Cluster count for KMeans")
    parser.add_argument("--topics", type=int, default=8, help="Topic count for NMF")
    parser.add_argument(
        "--max-features",
        type=int,
        default=5000,
        help="Max TF-IDF features for advanced analysis",
    )
    parser.add_argument(
        "--min-df",
        type=int,
        default=3,
        help="Min document frequency for TF-IDF",
    )
    parser.add_argument(
        "--print-json",
        action="store_true",
        help="Print the report JSON to stdout",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    advanced_options = {
        "n_clusters": args.clusters,
        "n_topics": args.topics,
        "max_features": args.max_features,
        "min_df": args.min_df,
    }
    payload = get_analysis_payload(
        data_dir=Path(args.data_dir),
        output_dir=Path(args.output_dir),
        top_n=args.top_n,
        include_advanced=args.advanced,
        advanced_options=advanced_options,
    )

    report = payload["report"]
    artifacts = payload.get("artifacts", {})

    print(f"Total jobs: {report['meta']['total_jobs']}")
    print(f"Files: {', '.join(report['meta']['files'])}")
    print("Artifacts:")
    for key, path in artifacts.items():
        print(f"  - {key}: {path}")

    advanced_meta = report.get("advanced_ml_nlp", {}).get("meta")
    if advanced_meta:
        print("Advanced ML/NLP meta:")
        for key, value in advanced_meta.items():
            print(f"  - {key}: {value}")

    if args.print_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
