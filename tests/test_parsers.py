from ingestion.parsers import (
	normalize_text,
	parse_bool,
	parse_decimal,
	parse_job_skills,
	parse_job_type_skills,
)


def test_parse_job_skills_valid_list() -> None:
	raw = "['python', 'sql', 'airflow']"
	assert parse_job_skills(raw) == ["python", "sql", "airflow"]


def test_parse_job_skills_invalid_value() -> None:
	assert parse_job_skills("not-a-list") is None


def test_parse_job_type_skills_valid_dict() -> None:
	raw = "{'core': ['python', 'sql'], 'cloud': ['aws']}"
	assert parse_job_type_skills(raw) == {
		"core": ["python", "sql"],
		"cloud": ["aws"],
	}


def test_parse_job_type_skills_ignores_empty_values() -> None:
	raw = "{'core': ['python', '  '], '': ['x'], 'other': []}"
	assert parse_job_type_skills(raw) == {"core": ["python"]}


def test_parse_bool_variants() -> None:
	assert parse_bool("True") is True
	assert parse_bool("0") is False
	assert parse_bool("unknown") is None


def test_parse_decimal_variants() -> None:
	assert str(parse_decimal("1234.50")) == "1234.50"
	assert parse_decimal("") is None
	assert parse_decimal("bad-value") is None


def test_normalize_text() -> None:
	assert normalize_text("  Data Engineer  ") == "Data Engineer"
	assert normalize_text("   ") is None
