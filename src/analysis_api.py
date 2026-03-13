from __future__ import annotations

import csv
import json
import re
import statistics
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.cluster import KMeans
from sklearn.decomposition import NMF, TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer

try:
	import jieba
except Exception:
	jieba = None

CSV_SUFFIX = "_jobs.csv"
SAMPLE_SUFFIX = "_sample.csv"


def discover_data_files(data_dir: str | Path) -> list[Path]:
	"""Find all full job CSV files under data directory."""
	root = Path(data_dir)
	files = []
	for path in sorted(root.glob(f"*{CSV_SUFFIX}")):
		if path.name.endswith(SAMPLE_SUFFIX):
			continue
		files.append(path)
	return files


def _split_pipe(value: str) -> list[str]:
	if not value:
		return []
	return [item.strip() for item in value.split("|") if item.strip()]


def load_jobs(csv_path: str | Path) -> list[dict[str, Any]]:
	"""Load normalized jobs from a single CSV file."""
	path = Path(csv_path)
	jobs: list[dict[str, Any]] = []
	with path.open("r", encoding="utf-8-sig", newline="") as fp:
		reader = csv.DictReader(fp)
		for row in reader:
			row = {k: (v or "").strip() for k, v in row.items()}
			row["work_cities_list"] = _split_pipe(row.get("work_cities", ""))
			row["tags_list"] = _split_pipe(row.get("tags", ""))
			row["source_file"] = path.name
			jobs.append(row)
	return jobs


def load_all_jobs(data_dir: str | Path) -> list[dict[str, Any]]:
	"""Load jobs from all full datasets."""
	jobs: list[dict[str, Any]] = []
	for file in discover_data_files(data_dir):
		jobs.extend(load_jobs(file))
	return jobs


def _top_counter(values: list[str], top_n: int) -> list[dict[str, Any]]:
	counter = Counter(v for v in values if v)
	return [
		{"name": name, "count": count}
		for name, count in counter.most_common(top_n)
	]


def analyze_overview(jobs: list[dict[str, Any]], top_n: int = 15) -> dict[str, Any]:
	"""Build high-level distribution analysis for jobs."""
	companies = [job.get("company", "") for job in jobs]
	recruit_types = [job.get("recruit_type", "") for job in jobs]
	categories = [job.get("job_category", "") for job in jobs]
	functions = [job.get("job_function", "") for job in jobs]
	cities = [job.get("work_city", "") for job in jobs]
	titles = [job.get("title", "") for job in jobs]

	multi_city_count = sum(
		1 for job in jobs if len(job.get("work_cities_list", [])) > 1
	)
	multi_city_ratio = round(multi_city_count / len(jobs), 4) if jobs else 0.0

	return {
		"total_jobs": len(jobs),
		"company_count": len({c for c in companies if c}),
		"multi_city_jobs": multi_city_count,
		"multi_city_ratio": multi_city_ratio,
		"by_company": _top_counter(companies, top_n=top_n),
		"by_recruit_type": _top_counter(recruit_types, top_n=top_n),
		"by_job_category": _top_counter(categories, top_n=top_n),
		"by_job_function": _top_counter(functions, top_n=top_n),
		"by_work_city": _top_counter(cities, top_n=top_n),
		"top_titles": _top_counter(titles, top_n=top_n),
	}


def analyze_quality(jobs: list[dict[str, Any]]) -> dict[str, Any]:
	"""Evaluate missing fields and duplicate rates."""
	if not jobs:
		return {
			"missing_rate": {},
			"duplicates": {},
			"text_length": {},
		}

	fields = [
		"company",
		"job_id",
		"title",
		"recruit_type",
		"job_category",
		"work_city",
		"responsibilities",
		"requirements",
		"detail_url",
		"publish_time",
	]

	total = len(jobs)
	missing_rate = {}
	for field in fields:
		missing = sum(1 for job in jobs if not job.get(field, "").strip())
		missing_rate[field] = {
			"missing": missing,
			"missing_rate": round(missing / total, 4),
		}

	company_jobid_counter = Counter(
		(job.get("company", ""), job.get("job_id", ""))
		for job in jobs
		if job.get("job_id", "").strip()
	)
	dup_company_jobid = sum(count - 1 for count in company_jobid_counter.values() if count > 1)

	detail_url_counter = Counter(
		job.get("detail_url", "") for job in jobs if job.get("detail_url", "").strip()
	)
	dup_detail_url = sum(count - 1 for count in detail_url_counter.values() if count > 1)

	duplicates = {
		"duplicate_company_job_id_rows": dup_company_jobid,
		"duplicate_detail_url_rows": dup_detail_url,
	}

	length_fields = ["responsibilities", "requirements", "bonus_points"]
	text_length = {}
	for field in length_fields:
		lengths = [len(job.get(field, "")) for job in jobs if job.get(field, "")]
		if not lengths:
			text_length[field] = {"count": 0, "avg": 0, "median": 0, "p90": 0}
			continue
		sorted_lengths = sorted(lengths)
		p90_index = max(0, int(len(sorted_lengths) * 0.9) - 1)
		text_length[field] = {
			"count": len(sorted_lengths),
			"avg": round(statistics.mean(sorted_lengths), 2),
			"median": round(statistics.median(sorted_lengths), 2),
			"p90": sorted_lengths[p90_index],
		}

	return {
		"missing_rate": missing_rate,
		"duplicates": duplicates,
		"text_length": text_length,
	}


DEFAULT_SKILL_KEYWORDS = [
	"python",
	"java",
	"c++",
	"go",
	"javascript",
	"typescript",
	"sql",
	"spark",
	"hadoop",
	"pytorch",
	"tensorflow",
	"llm",
	"nlp",
	"cv",
	"机器学习",
	"深度学习",
	"算法",
	"数据分析",
	"前端",
	"后端",
	"测试",
	"运维",
	"产品",
	"设计",
]

CAREER_TRACK_RULES = {
	"algorithm_ai": ["算法", "机器学习", "深度学习", "nlp", "llm", "cv", "推荐", "大模型"],
	"backend": ["后端", "服务端", "java", "go", "c++", "python", "分布式"],
	"frontend": ["前端", "javascript", "typescript", "react", "vue", "web"],
	"data": ["数据", "数仓", "spark", "hadoop", "etl", "bi", "分析"],
	"product_ops": ["产品", "运营", "增长", "策略", "用户", "商业"],
	"qa_test": ["测试", "qa", "自动化测试", "质量"],
	"design": ["设计", "交互", "视觉", "ui", "ux", "美术"],
	"security": ["安全", "风控", "攻防", "隐私", "合规"],
	"infra_hardware": ["基础架构", "云", "网络", "硬件", "芯片", "嵌入式"],
}

MEANINGLESS_TERMS = {
	"以及",
	"相关",
	"能力",
	"负责",
	"熟悉",
	"优先",
	"岗位",
	"要求",
	"工作",
	"实习",
	"同学",
	"技术",
	"系统",
	"开发",
	"产品",
	"经验",
	"能够",
	"进行",
	"我们",
	"团队",
	"良好",
	"掌握",
	"candidate",
	"intern",
}


def _normalize_city(city: str) -> str:
	if not city:
		return "Unknown"
	city = city.strip()
	if city.startswith("深圳"):
		return "深圳"
	if city.startswith("上海"):
		return "上海"
	if city.startswith("北京"):
		return "北京"
	if city.startswith("杭州"):
		return "杭州"
	if city.startswith("广州"):
		return "广州"
	return city


def _safe_ratio(numerator: int, denominator: int) -> float:
	if denominator <= 0:
		return 0.0
	return round(numerator / denominator, 4)


def _detect_career_track(job: dict[str, Any]) -> str:
	text = " ".join(
		[
			job.get("title", ""),
			job.get("job_category", ""),
			job.get("requirements", ""),
			job.get("tags", ""),
		]
	).lower()

	best_track = "other"
	best_score = 0
	for track, rules in CAREER_TRACK_RULES.items():
		score = sum(1 for keyword in rules if keyword.lower() in text)
		if score > best_score:
			best_track = track
			best_score = score

	if best_score == 0:
		category = job.get("job_category", "").strip()
		if category:
			return category.lower()
	return best_track


def analyze_career_guidance(jobs: list[dict[str, Any]], top_n: int = 8) -> dict[str, Any]:
	"""Generate practical guidance signals for job seeking and planning."""
	if not jobs:
		return {
			"career_track_demand": [],
			"city_opportunity": [],
			"company_track_focus": [],
			"internship_ratio_by_track": [],
			"actionable_suggestions": [],
		}

	track_counter: Counter[str] = Counter()
	city_counter: Counter[str] = Counter()
	city_track_diversity: dict[str, set[str]] = {}
	company_track_counter: dict[str, Counter[str]] = {}
	track_total_counter: Counter[str] = Counter()
	track_intern_counter: Counter[str] = Counter()

	for job in jobs:
		track = _detect_career_track(job)
		track_counter[track] += 1

		city = _normalize_city(job.get("work_city", ""))
		city_counter[city] += 1
		city_track_diversity.setdefault(city, set()).add(track)

		company = job.get("company", "") or "Unknown"
		company_track_counter.setdefault(company, Counter())
		company_track_counter[company][track] += 1

		track_total_counter[track] += 1
		recruit_type = job.get("recruit_type", "").lower()
		if any(k in recruit_type for k in ["实习", "intern"]):
			track_intern_counter[track] += 1

	career_track_demand = [
		{"track": track, "count": count, "share": _safe_ratio(count, len(jobs))}
		for track, count in track_counter.most_common(top_n)
	]

	city_opportunity = []
	for city, count in city_counter.items():
		diversity = len(city_track_diversity.get(city, set()))
		score = round(count * (1 + 0.12 * diversity), 2)
		city_opportunity.append(
			{
				"city": city,
				"job_count": count,
				"track_diversity": diversity,
				"opportunity_score": score,
			}
		)
	city_opportunity.sort(key=lambda x: x["opportunity_score"], reverse=True)

	company_track_focus = []
	for company, counter in company_track_counter.items():
		total = sum(counter.values())
		top_track, top_count = counter.most_common(1)[0]
		company_track_focus.append(
			{
				"company": company,
				"total_jobs": total,
				"primary_track": top_track,
				"primary_track_share": _safe_ratio(top_count, total),
			}
		)
	company_track_focus.sort(key=lambda x: x["total_jobs"], reverse=True)

	internship_ratio_by_track = []
	for track, total in track_total_counter.items():
		intern = track_intern_counter.get(track, 0)
		internship_ratio_by_track.append(
			{
				"track": track,
				"internship_ratio": _safe_ratio(intern, total),
				"total": total,
			}
		)
	internship_ratio_by_track.sort(key=lambda x: x["total"], reverse=True)

	actionable_suggestions = []
	for item in career_track_demand[:3]:
		track = item["track"]
		ratio_info = next((x for x in internship_ratio_by_track if x["track"] == track), None)
		if ratio_info and ratio_info["internship_ratio"] >= 0.75:
			actionable_suggestions.append(
				f"{track} 方向岗位需求高且实习占比高，建议优先通过实习路径切入。"
			)
		else:
			actionable_suggestions.append(
				f"{track} 方向岗位需求高，建议重点准备项目经历与匹配技能关键词。"
			)

	if city_opportunity:
		top_city = city_opportunity[0]["city"]
		actionable_suggestions.append(
			f"地域选择上，{top_city} 的综合机会指数最高，可作为优先投递城市。"
		)

	return {
		"career_track_demand": career_track_demand,
		"city_opportunity": city_opportunity[: top_n + 2],
		"company_track_focus": company_track_focus,
		"internship_ratio_by_track": internship_ratio_by_track[:top_n],
		"actionable_suggestions": actionable_suggestions,
	}


def analyze_skills(
	jobs: list[dict[str, Any]],
	top_n: int = 30,
	keywords: list[str] | None = None,
) -> dict[str, Any]:
	"""Extract simple skill heatmap by keyword matching."""
	if keywords is None:
		keywords = DEFAULT_SKILL_KEYWORDS

	normalized_keywords = [k.lower() for k in keywords]
	all_texts = []
	for job in jobs:
		text = " ".join(
			[
				job.get("title", ""),
				job.get("requirements", ""),
				job.get("bonus_points", ""),
				job.get("responsibilities", ""),
				" ".join(job.get("tags_list", [])),
			]
		).lower()
		all_texts.append(text)

	hit_counter: Counter[str] = Counter()
	for text in all_texts:
		for kw in normalized_keywords:
			if kw and kw in text:
				hit_counter[kw] += 1

	token_counter: Counter[str] = Counter()
	stopwords = {
		"and",
		"the",
		"for",
		"with",
		"you",
		"are",
		"to",
		"in",
		"of",
		"or",
		"a",
		"an",
		"on",
		"at",
	}
	token_pattern = re.compile(r"[a-zA-Z][a-zA-Z0-9_+#.-]{1,24}")
	for text in all_texts:
		for token in token_pattern.findall(text):
			token = token.lower()
			if token in stopwords or token.isdigit():
				continue
			token_counter[token] += 1

	return {
		"keyword_hits": [
			{"keyword": keyword, "count": count}
			for keyword, count in hit_counter.most_common(top_n)
		],
		"top_english_tokens": [
			{"token": token, "count": count}
			for token, count in token_counter.most_common(top_n)
		],
	}


def _compose_job_text(job: dict[str, Any]) -> str:
	parts = [
		job.get("title", ""),
		job.get("job_category", ""),
		job.get("job_function", ""),
		job.get("responsibilities", ""),
		job.get("requirements", ""),
		job.get("bonus_points", ""),
		" ".join(job.get("tags_list", [])),
	]
	return " ".join(p for p in parts if p).strip()


def _tokenize_mixed_text(text: str) -> list[str]:
	"""Tokenize Chinese and English text into readable words for NLP tasks."""
	if not text:
		return []

	tokens: list[str] = []
	english_tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9_+#.-]{1,24}", text.lower())
	tokens.extend(english_tokens)

	if jieba is not None:
		for token in jieba.lcut(text):
			token = token.strip().lower()
			if not token:
				continue
			if re.fullmatch(r"[\W_]+", token):
				continue
			if len(token) == 1 and not re.fullmatch(r"[a-zA-Z0-9]", token):
				continue
			if token in MEANINGLESS_TERMS:
				continue
			if token.isdigit():
				continue
			tokens.append(token)
	else:
		chinese_tokens = re.findall(r"[\u4e00-\u9fff]{2,}", text)
		tokens.extend([t for t in chinese_tokens if t not in MEANINGLESS_TERMS])

	return tokens


def _make_cluster_name(top_categories: list[dict[str, Any]], top_terms: list[str]) -> str:
	category = "General"
	if top_categories:
		category = top_categories[0].get("name") or "General"

	filtered_terms = [
		term
		for term in top_terms
		if term
		and term not in MEANINGLESS_TERMS
		and len(term) > 1
		and not re.fullmatch(r"\d+", term)
	]
	if filtered_terms:
		return f"{category}::{filtered_terms[0]}"
	return f"{category}::core"


def analyze_ml_nlp(
	jobs: list[dict[str, Any]],
	max_features: int = 5000,
	min_df: int = 3,
	n_clusters: int = 8,
	n_topics: int = 8,
	top_terms: int = 12,
) -> dict[str, Any]:
	"""Run TF-IDF based clustering and topic extraction for deeper NLP analysis."""
	if not jobs:
		return {
			"meta": {"sample_size": 0},
			"clusters": [],
			"topics": [],
			"embeddings_2d": [],
		}

	texts = [_compose_job_text(job) for job in jobs]
	valid_idx = [i for i, txt in enumerate(texts) if txt]
	if not valid_idx:
		return {
			"meta": {"sample_size": 0},
			"clusters": [],
			"topics": [],
			"embeddings_2d": [],
		}

	filtered_jobs = [jobs[i] for i in valid_idx]
	filtered_texts = [texts[i] for i in valid_idx]

	vectorizer = TfidfVectorizer(
		tokenizer=_tokenize_mixed_text,
		token_pattern=None,
		lowercase=True,
		min_df=min_df,
		max_features=max_features,
	)
	X = vectorizer.fit_transform(filtered_texts)
	features = vectorizer.get_feature_names_out()

	if X.shape[0] < 2 or X.shape[1] < 2:
		return {
			"meta": {
				"sample_size": len(filtered_jobs),
				"vector_features": int(X.shape[1]),
			},
			"clusters": [],
			"topics": [],
			"embeddings_2d": [],
		}

	cluster_k = max(2, min(n_clusters, X.shape[0]))
	kmeans = KMeans(n_clusters=cluster_k, random_state=42, n_init=10)
	labels = kmeans.fit_predict(X)

	cluster_rows: list[dict[str, Any]] = []
	for cluster_id in range(cluster_k):
		indices = [i for i, label in enumerate(labels) if label == cluster_id]
		if not indices:
			continue

		center = kmeans.cluster_centers_[cluster_id]
		top_idx = np.argsort(center)[::-1][:top_terms]
		top_terms_list = [features[i] for i in top_idx]

		companies = Counter(filtered_jobs[i].get("company", "") for i in indices)
		categories = Counter(filtered_jobs[i].get("job_category", "") for i in indices)

		cluster_rows.append(
			{
				"cluster_id": int(cluster_id),
				"size": len(indices),
				"top_terms": top_terms_list,
				"top_companies": [
					{"name": name, "count": count}
					for name, count in companies.most_common(5)
				],
				"top_categories": [
					{"name": name, "count": count}
					for name, count in categories.most_common(5)
				],
			}
		)

	for row in cluster_rows:
		row["cluster_name"] = _make_cluster_name(row.get("top_categories", []), row.get("top_terms", []))

	cluster_name_map = {row["cluster_id"]: row["cluster_name"] for row in cluster_rows}

	topic_k = max(2, min(n_topics, X.shape[0], X.shape[1]))
	nmf = NMF(n_components=topic_k, init="nndsvda", random_state=42, max_iter=400)
	W = nmf.fit_transform(X)
	H = nmf.components_

	topics: list[dict[str, Any]] = []
	for topic_id in range(topic_k):
		top_idx = np.argsort(H[topic_id])[::-1][:top_terms]
		topic_terms = [features[i] for i in top_idx]
		mean_weight = float(np.mean(W[:, topic_id]))
		topics.append(
			{
				"topic_id": int(topic_id),
				"mean_weight": round(mean_weight, 6),
				"top_terms": topic_terms,
			}
		)

	svd = TruncatedSVD(n_components=2, random_state=42)
	coords = svd.fit_transform(X)

	max_points = 4000
	embeddings_2d: list[dict[str, Any]] = []
	for i in range(min(len(filtered_jobs), max_points)):
		job = filtered_jobs[i]
		embeddings_2d.append(
			{
				"x": float(coords[i, 0]),
				"y": float(coords[i, 1]),
				"cluster_id": int(labels[i]),
				"cluster_name": cluster_name_map.get(int(labels[i]), f"cluster_{int(labels[i])}"),
				"company": job.get("company", ""),
				"job_category": job.get("job_category", ""),
				"title": job.get("title", ""),
			}
		)

	return {
		"meta": {
			"sample_size": len(filtered_jobs),
			"vector_features": int(X.shape[1]),
			"cluster_count": cluster_k,
			"topic_count": topic_k,
			"explained_variance_2d": round(float(svd.explained_variance_ratio_.sum()), 6),
		},
		"clusters": sorted(cluster_rows, key=lambda x: x["size"], reverse=True),
		"topics": topics,
		"embeddings_2d": embeddings_2d,
	}


def build_analysis_report(
	data_dir: str | Path,
	top_n: int = 15,
	include_advanced: bool = False,
	advanced_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
	"""Single entrypoint for notebook and frontend service calls."""
	jobs = load_all_jobs(data_dir)
	files = [path.name for path in discover_data_files(data_dir)]

	report = {
		"meta": {
			"generated_at": datetime.now(timezone.utc).isoformat(),
			"data_dir": str(Path(data_dir).resolve()),
			"files": files,
			"total_jobs": len(jobs),
		},
		"overview": analyze_overview(jobs, top_n=top_n),
		"quality": analyze_quality(jobs),
		"skills": analyze_skills(jobs, top_n=max(20, top_n)),
		"career_guidance": analyze_career_guidance(jobs, top_n=max(8, top_n // 2)),
	}
	if include_advanced:
		opts = advanced_options or {}
		report["advanced_ml_nlp"] = analyze_ml_nlp(jobs, **opts)
	return report


def export_analysis_artifacts(
	report: dict[str, Any],
	output_dir: str | Path,
) -> dict[str, str]:
	"""Export machine-readable artifacts for downstream frontend/backend use."""
	out_dir = Path(output_dir)
	out_dir.mkdir(parents=True, exist_ok=True)

	report_json = out_dir / "analysis_report.json"
	report_json.write_text(
		json.dumps(report, ensure_ascii=False, indent=2),
		encoding="utf-8",
	)

	outputs = {"analysis_report": str(report_json)}

	table_mappings = {
		"company_distribution.csv": report.get("overview", {}).get("by_company", []),
		"city_distribution.csv": report.get("overview", {}).get("by_work_city", []),
		"job_category_distribution.csv": report.get("overview", {}).get("by_job_category", []),
		"skill_keyword_hits.csv": report.get("skills", {}).get("keyword_hits", []),
	}
	advanced = report.get("advanced_ml_nlp", {})
	if advanced:
		table_mappings["ml_embeddings_2d.csv"] = advanced.get("embeddings_2d", [])
		table_mappings["ml_cluster_summary.csv"] = [
			{
				"cluster_id": row.get("cluster_id"),
				"cluster_name": row.get("cluster_name"),
				"size": row.get("size"),
				"top_terms": "|".join(row.get("top_terms", [])),
			}
			for row in advanced.get("clusters", [])
		]
		table_mappings["career_track_demand.csv"] = report.get("career_guidance", {}).get("career_track_demand", [])
		table_mappings["city_opportunity.csv"] = report.get("career_guidance", {}).get("city_opportunity", [])
		table_mappings["ml_topic_summary.csv"] = [
			{
				"topic_id": row.get("topic_id"),
				"mean_weight": row.get("mean_weight"),
				"top_terms": "|".join(row.get("top_terms", [])),
			}
			for row in advanced.get("topics", [])
		]

	for filename, rows in table_mappings.items():
		path = out_dir / filename
		_write_rows(path, rows)
		outputs[filename.replace(".csv", "")] = str(path)

	return outputs


def _write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
	if not rows:
		path.write_text("", encoding="utf-8")
		return
	headers = list(rows[0].keys())
	with path.open("w", encoding="utf-8", newline="") as fp:
		writer = csv.DictWriter(fp, fieldnames=headers)
		writer.writeheader()
		writer.writerows(rows)


def get_analysis_payload(
	data_dir: str | Path,
	output_dir: str | Path | None = None,
	top_n: int = 15,
	include_advanced: bool = False,
	advanced_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
	"""
	Frontend-facing stable interface.

	Returns a dict with report content and optional exported file paths.
	"""
	report = build_analysis_report(
		data_dir=data_dir,
		top_n=top_n,
		include_advanced=include_advanced,
		advanced_options=advanced_options,
	)
	payload = {"report": report}
	if output_dir is not None:
		payload["artifacts"] = export_analysis_artifacts(report, output_dir)
	return payload

