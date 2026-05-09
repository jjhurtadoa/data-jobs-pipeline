"""Logging setup for ingestion tasks."""

from __future__ import annotations

import logging


def configure_logging(level: str = "INFO") -> None:
	"""Configure root logger only once."""
	root_logger = logging.getLogger()
	if root_logger.handlers:
		root_logger.setLevel(level.upper())
		return

	logging.basicConfig(
		level=level.upper(),
		format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
	)
