"""Database utilities for ingestion."""

from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import psycopg
from psycopg.connection import Connection
from psycopg.types.json import Jsonb


@dataclass(frozen=True)
class DbConfig:
	"""Configuration for PostgreSQL connectivity."""

	host: str
	port: int
	dbname: str
	user: str
	password: str

	@classmethod
	def from_env(cls) -> "DbConfig":
		return cls(
			host=os.getenv("DB_HOST", "localhost"),
			port=int(os.getenv("DB_PORT", "5432")),
			dbname=os.getenv("DB_NAME", "jobs_db"),
			user=os.getenv("DB_USER", "postgres"),
			password=os.getenv("DB_PASSWORD", "postgres"),
		)


def get_connection(config: DbConfig) -> Connection[Any]:
	"""Create a PostgreSQL connection using the provided config."""
	return psycopg.connect(
		host=config.host,
		port=config.port,
		dbname=config.dbname,
		user=config.user,
		password=config.password,
	)


def insert_jobs_batch(conn: Connection[Any], rows: list[dict[str, Any]]) -> int:
	"""Insert a batch of raw job rows and return affected count."""
	if not rows:
		return 0

	sql = """
	INSERT INTO raw.jobs (
		job_title_short,
		job_title,
		job_location,
		job_via,
		job_schedule_type,
		job_work_from_home,
		search_location,
		job_posted_date,
		job_no_degree_mention,
		job_health_insurance,
		job_country,
		salary_rate,
		salary_year_avg,
		salary_hour_avg,
		company_name,
		job_skills,
		job_type_skills
	)
	VALUES (
		%(job_title_short)s,
		%(job_title)s,
		%(job_location)s,
		%(job_via)s,
		%(job_schedule_type)s,
		%(job_work_from_home)s,
		%(search_location)s,
		%(job_posted_date)s,
		%(job_no_degree_mention)s,
		%(job_health_insurance)s,
		%(job_country)s,
		%(salary_rate)s,
		%(salary_year_avg)s,
		%(salary_hour_avg)s,
		%(company_name)s,
		%(job_skills)s,
		%(job_type_skills)s
	)
	"""

	payload: list[dict[str, Any]] = []
	for row in rows:
		payload.append(
			{
				**row,
				"salary_year_avg": _to_decimal_or_none(row.get("salary_year_avg")),
				"salary_hour_avg": _to_decimal_or_none(row.get("salary_hour_avg")),
				"job_skills": Jsonb(row["job_skills"]) if row.get("job_skills") is not None else None,
				"job_type_skills": Jsonb(row["job_type_skills"]) if row.get("job_type_skills") is not None else None,
			}
		)

	with conn.cursor() as cur:
		cur.executemany(sql, payload)

	return len(rows)


def get_jobs_count(conn: Connection[Any]) -> int:
	"""Return current number of rows in raw.jobs."""
	with conn.cursor() as cur:
		cur.execute("SELECT count(*) FROM raw.jobs")
		result = cur.fetchone()
		return int(result[0]) if result else 0


def is_file_already_ingested(conn: Connection[Any], file_md5: str) -> bool:
	"""Check whether a completed ingestion already exists for file fingerprint."""
	with conn.cursor() as cur:
		cur.execute(
			"""
			SELECT 1
			FROM raw.ingestion_log
			WHERE file_md5 = %s AND status = 'completed'
			LIMIT 1
			""",
			(file_md5,),
		)
		return cur.fetchone() is not None


def register_ingestion_log(
	conn: Connection[Any],
	*,
	file_md5: str,
	file_path: str,
	source_name: str,
	status: str,
	total_rows: int,
	inserted_rows: int,
	parse_warnings: int,
	job_skills_missing: int,
	job_skills_invalid: int,
	job_type_skills_missing: int,
	job_type_skills_invalid: int,
) -> None:
	"""Register ingestion execution outcome in raw.ingestion_log."""
	with conn.cursor() as cur:
		cur.execute(
			"""
			INSERT INTO raw.ingestion_log (
				file_md5,
				file_path,
				source_name,
				status,
				total_rows,
				inserted_rows,
				parse_warnings,
				job_skills_missing,
				job_skills_invalid,
				job_type_skills_missing,
				job_type_skills_invalid,
				finished_at
			)
			VALUES (
				%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW()
			)
			ON CONFLICT (file_md5)
			DO UPDATE SET
				status = EXCLUDED.status,
				total_rows = EXCLUDED.total_rows,
				inserted_rows = EXCLUDED.inserted_rows,
				parse_warnings = EXCLUDED.parse_warnings,
				job_skills_missing = EXCLUDED.job_skills_missing,
				job_skills_invalid = EXCLUDED.job_skills_invalid,
				job_type_skills_missing = EXCLUDED.job_type_skills_missing,
				job_type_skills_invalid = EXCLUDED.job_type_skills_invalid,
				finished_at = NOW()
			""",
			(
				file_md5,
				file_path,
				source_name,
				status,
				total_rows,
				inserted_rows,
				parse_warnings,
				job_skills_missing,
				job_skills_invalid,
				job_type_skills_missing,
				job_type_skills_invalid,
			),
		)


def _to_decimal_or_none(value: Any) -> Decimal | None:
	if value is None:
		return None
	if isinstance(value, Decimal):
		return value
	return Decimal(str(value))
