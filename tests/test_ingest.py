from pathlib import Path

from ingestion.ingest import build_job_record, chunked, compute_file_md5
import ingestion.ingest as ingest_module


def test_build_job_record_maps_expected_types() -> None:
	source = {
		"job_title_short": "Data Engineer",
		"job_title": "Senior Data Engineer",
		"job_location": "Remote",
		"job_via": "LinkedIn",
		"job_schedule_type": "Full-time",
		"job_work_from_home": "True",
		"search_location": "Colombia",
		"job_posted_date": "2024-10-10 10:00:00",
		"job_no_degree_mention": "False",
		"job_health_insurance": "True",
		"job_country": "Colombia",
		"salary_rate": "year",
		"salary_year_avg": "120000",
		"salary_hour_avg": "",
		"company_name": "Acme",
		"job_skills": "['python','sql']",
		"job_type_skills": "{'core':['python','sql']}",
	}

	record, warnings_count, parse_profile = build_job_record(source)

	assert warnings_count == 0
	assert parse_profile == {
		"job_skills_missing": 0,
		"job_skills_invalid": 0,
		"job_type_skills_missing": 0,
		"job_type_skills_invalid": 0,
	}
	assert record["job_work_from_home"] is True
	assert record["job_no_degree_mention"] is False
	assert record["salary_year_avg"] is not None
	assert record["salary_hour_avg"] is None
	assert record["job_skills"] == ["python", "sql"]
	assert record["job_type_skills"] == {"core": ["python", "sql"]}


def test_build_job_record_counts_parse_warnings() -> None:
	source = {
		"job_skills": "definitely-not-a-list",
		"job_type_skills": "definitely-not-a-dict",
	}

	_, warnings_count, parse_profile = build_job_record(source)
	assert warnings_count == 2
	assert parse_profile == {
		"job_skills_missing": 0,
		"job_skills_invalid": 1,
		"job_type_skills_missing": 0,
		"job_type_skills_invalid": 1,
	}


def test_build_job_record_profiles_missing_semistructured_values() -> None:
	source = {
		"job_skills": "",
		"job_type_skills": None,
	}

	_, warnings_count, parse_profile = build_job_record(source)
	assert warnings_count == 0
	assert parse_profile == {
		"job_skills_missing": 1,
		"job_skills_invalid": 0,
		"job_type_skills_missing": 1,
		"job_type_skills_invalid": 0,
	}


def test_compute_file_md5_is_deterministic(tmp_path: Path) -> None:
	file_path = tmp_path / "sample.txt"
	file_path.write_text("abc123", encoding="utf-8")
	first = compute_file_md5(str(file_path))
	second = compute_file_md5(str(file_path))
	assert first == second


def test_chunked_splits_list() -> None:
	items = [{"x": i} for i in range(5)]
	chunks = list(chunked(items, 2))
	assert len(chunks) == 3
	assert [len(chunk) for chunk in chunks] == [2, 2, 1]


def test_chunked_raises_on_invalid_size() -> None:
	try:
		list(chunked([], 0))
	except ValueError as exc:
		assert "greater than 0" in str(exc)
	else:
		raise AssertionError("chunked should raise ValueError when size <= 0")


def test_ingest_skip_does_not_rewrite_log_or_read_csv(monkeypatch) -> None:
	class _ConnCtx:
		def __enter__(self):
			return object()

		def __exit__(self, exc_type, exc, tb):
			return False

	register_calls = {"count": 0}

	monkeypatch.setattr(ingest_module.DbConfig, "from_env", classmethod(lambda cls: object()))
	monkeypatch.setattr(ingest_module, "get_connection", lambda _cfg: _ConnCtx())
	monkeypatch.setattr(ingest_module, "compute_file_md5", lambda _path: "same-md5")
	monkeypatch.setattr(ingest_module, "is_file_already_ingested", lambda _conn, _md5: True)

	def _register_stub(*args, **kwargs):
		register_calls["count"] += 1

	monkeypatch.setattr(ingest_module, "register_ingestion_log", _register_stub)

	def _read_csv_fail(*args, **kwargs):
		raise AssertionError("CSV must not be read on skip path")

	monkeypatch.setattr(ingest_module.pd, "read_csv", _read_csv_fail)

	stats = ingest_module.ingest_csv_to_raw(csv_path="data/data_jobs.csv")

	assert stats.skipped is True
	assert stats.total_rows == 0
	assert stats.inserted_rows == 0
	assert register_calls["count"] == 0
