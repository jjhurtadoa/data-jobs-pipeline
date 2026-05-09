"""Parsing utilities for raw ingestion."""

from __future__ import annotations

import ast
import math
from decimal import Decimal, InvalidOperation
from typing import Any


def is_null_like(value: Any) -> bool:
	"""Return True when value should be treated as null."""
	if value is None:
		return True
	if isinstance(value, float) and math.isnan(value):
		return True
	if isinstance(value, str) and value.strip().lower() in {"", "null", "none", "nan"}:
		return True
	return False


def normalize_text(value: Any) -> str | None:
	"""Normalize text values by trimming whitespace."""
	if is_null_like(value):
		return None
	text = str(value).strip()
	return text if text else None


def parse_bool(value: Any) -> bool | None:
	"""Parse typical boolean string representations."""
	if is_null_like(value):
		return None
	if isinstance(value, bool):
		return value
	normalized = str(value).strip().lower()
	if normalized in {"true", "t", "1", "yes", "y"}:
		return True
	if normalized in {"false", "f", "0", "no", "n"}:
		return False
	return None


def parse_decimal(value: Any) -> Decimal | None:
	"""Parse decimal values from CSV-compatible inputs."""
	if is_null_like(value):
		return None
	try:
		return Decimal(str(value).strip())
	except (InvalidOperation, ValueError):
		return None


def _parse_literal(value: Any) -> Any:
	"""Parse Python-like literal strings found in CSV fields."""
	if is_null_like(value):
		return None
	if isinstance(value, (list, dict)):
		return value
	if not isinstance(value, str):
		return None

	candidate = value.strip()
	if not candidate:
		return None

	try:
		return ast.literal_eval(candidate)
	except (ValueError, SyntaxError):
		return None


def parse_job_skills(value: Any) -> list[str] | None:
	"""Parse the job_skills column into a clean list of strings."""
	parsed = _parse_literal(value)
	if parsed is None:
		return None
	if not isinstance(parsed, list):
		return None

	cleaned: list[str] = []
	for item in parsed:
		normalized = normalize_text(item)
		if normalized is not None:
			cleaned.append(normalized)

	return cleaned or None


def parse_job_type_skills(value: Any) -> dict[str, list[str]] | None:
	"""Parse the job_type_skills column into a dict[str, list[str]]."""
	parsed = _parse_literal(value)
	if parsed is None:
		return None
	if not isinstance(parsed, dict):
		return None

	cleaned: dict[str, list[str]] = {}
	for raw_key, raw_values in parsed.items():
		key = normalize_text(raw_key)
		if key is None:
			continue

		values_list: list[str]
		if isinstance(raw_values, list):
			values_list = [v for v in (normalize_text(x) for x in raw_values) if v is not None]
		else:
			normalized_single = normalize_text(raw_values)
			values_list = [normalized_single] if normalized_single is not None else []

		if values_list:
			cleaned[key] = values_list

	return cleaned or None
