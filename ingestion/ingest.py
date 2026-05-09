"""CSV ingestion entrypoint for raw.jobs."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Iterable
import hashlib

import pandas as pd
from dotenv import load_dotenv

from ingestion.db import DbConfig, get_connection, insert_jobs_batch
from ingestion.db import get_jobs_count, is_file_already_ingested, register_ingestion_log
from ingestion.logging_config import configure_logging
from ingestion.parsers import (
	is_null_like,
	parse_bool,
	parse_decimal,
	parse_job_skills,
	parse_job_type_skills,
	normalize_text,
)

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class IngestionStats:
	total_rows: int
	inserted_rows: int
	parse_warnings: int
	job_skills_missing: int
	job_skills_invalid: int
	job_type_skills_missing: int
	job_type_skills_invalid: int
	file_md5: str
	skipped: bool


def main() -> None:
	load_dotenv(override=True)
	configure_logging(os.getenv("LOG_LEVEL", "INFO"))

	csv_path = os.getenv("CSV_PATH", "data/data_jobs.csv")
	batch_size = int(os.getenv("INGEST_BATCH_SIZE", "2000"))
	source_name = os.getenv("SOURCE_NAME", "local_csv")
	max_rows_raw = os.getenv("INGEST_MAX_ROWS")
	max_rows = int(max_rows_raw) if max_rows_raw else None

	stats = ingest_csv_to_raw(
		csv_path=csv_path,
		batch_size=batch_size,
		max_rows=max_rows,
		source_name=source_name,
	)
	LOGGER.info(
		"Ingestion finished | skipped=%s file_md5=%s total_rows=%s inserted_rows=%s parse_warnings=%s job_skills_missing=%s job_skills_invalid=%s job_type_skills_missing=%s job_type_skills_invalid=%s",
		stats.skipped,
		stats.file_md5,
		stats.total_rows,
		stats.inserted_rows,
		stats.parse_warnings,
		stats.job_skills_missing,
		stats.job_skills_invalid,
		stats.job_type_skills_missing,
		stats.job_type_skills_invalid,
	)


def ingest_csv_to_raw(
	csv_path: str,
	batch_size: int = 2000,
	max_rows: int | None = None,
	source_name: str = "local_csv",
) -> IngestionStats:
	"""Read CSV, normalize records, and load into raw.jobs."""
	file_md5 = compute_file_md5(csv_path)
	file_path = str(Path(csv_path).as_posix())

	db_config = DbConfig.from_env()
	with get_connection(db_config) as conn:
		if is_file_already_ingested(conn, file_md5):
			return IngestionStats(
				total_rows=0,
				inserted_rows=0,
				parse_warnings=0,
				job_skills_missing=0,
				job_skills_invalid=0,
				job_type_skills_missing=0,
				job_type_skills_invalid=0,
				file_md5=file_md5,
				skipped=True,
			)

	LOGGER.info("Reading CSV from %s", csv_path)
	parse_warnings = 0
	job_skills_missing = 0
	job_skills_invalid = 0
	job_type_skills_missing = 0
	job_type_skills_invalid = 0
	total_rows = 0
	processed_rows = 0

	read_csv_kwargs: dict[str, Any] = {"chunksize": batch_size}
	if max_rows is not None:
		read_csv_kwargs["nrows"] = max_rows

	with get_connection(db_config) as conn:
		rows_before = get_jobs_count(conn)
		for chunk in pd.read_csv(csv_path, **read_csv_kwargs):
			records: list[dict[str, Any]] = []
			for _, row in chunk.iterrows():
				record, warnings_count, parse_profile = build_job_record(row.to_dict())
				parse_warnings += warnings_count
				job_skills_missing += parse_profile["job_skills_missing"]
				job_skills_invalid += parse_profile["job_skills_invalid"]
				job_type_skills_missing += parse_profile["job_type_skills_missing"]
				job_type_skills_invalid += parse_profile["job_type_skills_invalid"]
				records.append(record)

			if records:
				insert_jobs_batch(conn, records)

			chunk_rows = len(chunk)
			total_rows += chunk_rows
			processed_rows += chunk_rows
			LOGGER.info("Processed %s rows", processed_rows)

		rows_after = get_jobs_count(conn)
		inserted_rows = rows_after - rows_before

		register_ingestion_log(
			conn,
			file_md5=file_md5,
			file_path=file_path,
			source_name=source_name,
			status="completed",
			total_rows=total_rows,
			inserted_rows=inserted_rows,
			parse_warnings=parse_warnings,
			job_skills_missing=job_skills_missing,
			job_skills_invalid=job_skills_invalid,
			job_type_skills_missing=job_type_skills_missing,
			job_type_skills_invalid=job_type_skills_invalid,
		)

	return IngestionStats(
		total_rows=total_rows,
		inserted_rows=inserted_rows,
		parse_warnings=parse_warnings,
		job_skills_missing=job_skills_missing,
		job_skills_invalid=job_skills_invalid,
		job_type_skills_missing=job_type_skills_missing,
		job_type_skills_invalid=job_type_skills_invalid,
		file_md5=file_md5,
		skipped=False,
	)


def build_job_record(
	source: dict[str, Any],
) -> tuple[dict[str, Any], int, dict[str, int]]:
	"""Build normalized row payload for raw.jobs insert."""
	warnings_count = 0
	parse_profile = {
		"job_skills_missing": 0,
		"job_skills_invalid": 0,
		"job_type_skills_missing": 0,
		"job_type_skills_invalid": 0,
	}

	raw_job_skills = source.get("job_skills")
	parsed_skills = parse_job_skills(raw_job_skills)
	if is_null_like(raw_job_skills):
		parse_profile["job_skills_missing"] = 1
	elif parsed_skills is None:
		parse_profile["job_skills_invalid"] = 1
		warnings_count += 1

	raw_job_type_skills = source.get("job_type_skills")
	parsed_type_skills = parse_job_type_skills(raw_job_type_skills)
	if is_null_like(raw_job_type_skills):
		parse_profile["job_type_skills_missing"] = 1
	elif parsed_type_skills is None:
		parse_profile["job_type_skills_invalid"] = 1
		warnings_count += 1

	return (
		{
			"job_title_short": normalize_text(source.get("job_title_short")),
			"job_title": normalize_text(source.get("job_title")),
			"job_location": normalize_text(source.get("job_location")),
			"job_via": normalize_text(source.get("job_via")),
			"job_schedule_type": normalize_text(source.get("job_schedule_type")),
			"job_work_from_home": parse_bool(source.get("job_work_from_home")),
			"search_location": normalize_text(source.get("search_location")),
			"job_posted_date": normalize_text(source.get("job_posted_date")),
			"job_no_degree_mention": parse_bool(source.get("job_no_degree_mention")),
			"job_health_insurance": parse_bool(source.get("job_health_insurance")),
			"job_country": normalize_text(source.get("job_country")),
			"salary_rate": normalize_text(source.get("salary_rate")),
			"salary_year_avg": parse_decimal(source.get("salary_year_avg")),
			"salary_hour_avg": parse_decimal(source.get("salary_hour_avg")),
			"company_name": normalize_text(source.get("company_name")),
			"job_skills": parsed_skills,
			"job_type_skills": parsed_type_skills,
		},

		warnings_count,
		parse_profile,
	)


def compute_file_md5(file_path: str) -> str:
	"""Compute deterministic MD5 fingerprint for a source file."""
	md5 = hashlib.md5()
	with open(file_path, "rb") as f:
		for chunk in iter(lambda: f.read(1024 * 1024), b""):
			md5.update(chunk)
	return md5.hexdigest()


def chunked(items: list[dict[str, Any]], size: int) -> Iterable[list[dict[str, Any]]]:
	"""Yield fixed-size chunks from a list."""
	if size <= 0:
		raise ValueError("size must be greater than 0")
	for i in range(0, len(items), size):
		yield items[i : i + size]


if __name__ == "__main__":
	main()

