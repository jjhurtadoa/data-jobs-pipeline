"""
Unit tests for the Airflow DAG structure.

These tests do NOT require a running Airflow instance or Docker.
They validate DAG integrity, task graph, and operator configuration
so that regressions in orchestration logic are caught in CI.
"""
from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Guard: skip the whole module if apache-airflow is not importable.
# Airflow is Linux-only; on Windows skip gracefully.
# In CI (GitHub Actions / Docker, Linux) the full suite runs.
# ---------------------------------------------------------------------------
try:
    from airflow.models import DagBag
    from airflow.operators.bash import BashOperator
except (ImportError, ModuleNotFoundError) as _airflow_err:
    pytest.skip(
        f"apache-airflow not importable in this environment: {_airflow_err}",
        allow_module_level=True,
    )


DAG_ID = "data_jobs_pipeline"
DAG_FILE = "airflow/dags/pipeline_dag.py"

EXPECTED_TASK_IDS = {"ingest_raw_jobs", "dbt_run_models", "dbt_run_tests"}
EXPECTED_DEPENDENCIES = [
    ("ingest_raw_jobs", "dbt_run_models"),
    ("dbt_run_models", "dbt_run_tests"),
]


@pytest.fixture(scope="module")
def dagbag():
    """Load the DAG bag from the dags folder."""
    return DagBag(dag_folder="airflow/dags", include_examples=False)


@pytest.fixture(scope="module")
def pipeline_dag(dagbag):
    """Return the target DAG object.

    Use dagbag.dags (in-memory parse result) to avoid hitting Airflow metadata
    DB in CI, where tables may not be initialized.
    """
    dag = dagbag.dags.get(DAG_ID)
    assert dag is not None, f"DAG '{DAG_ID}' not found. Import errors: {dagbag.import_errors}"
    return dag


# ---------------------------------------------------------------------------
# 1. Import health
# ---------------------------------------------------------------------------

def test_dag_no_import_errors(dagbag):
    """DagBag must load without any import errors."""
    assert dagbag.import_errors == {}, f"Import errors: {dagbag.import_errors}"


# ---------------------------------------------------------------------------
# 2. DAG metadata
# ---------------------------------------------------------------------------

def test_dag_exists(dagbag):
    assert DAG_ID in dagbag.dags, f"DAG '{DAG_ID}' not found in DagBag"


def test_dag_tags(pipeline_dag):
    assert "etl" in pipeline_dag.tags
    assert "dbt" in pipeline_dag.tags


def test_dag_catchup_disabled(pipeline_dag):
    assert pipeline_dag.catchup is False, "catchup must be False to avoid backfill storms"


def test_dag_max_active_runs(pipeline_dag):
    assert pipeline_dag.max_active_runs == 1, "max_active_runs must be 1 (idempotency)"


# ---------------------------------------------------------------------------
# 3. Task inventory
# ---------------------------------------------------------------------------

def test_task_count(pipeline_dag):
    assert len(pipeline_dag.tasks) == len(EXPECTED_TASK_IDS), (
        f"Expected {len(EXPECTED_TASK_IDS)} tasks, got {len(pipeline_dag.tasks)}"
    )


def test_task_ids(pipeline_dag):
    actual = {t.task_id for t in pipeline_dag.tasks}
    assert actual == EXPECTED_TASK_IDS


def test_all_tasks_are_bash_operators(pipeline_dag):
    for task in pipeline_dag.tasks:
        assert isinstance(task, BashOperator), (
            f"Task '{task.task_id}' is {type(task).__name__}, expected BashOperator"
        )


# ---------------------------------------------------------------------------
# 4. Task dependencies (topology)
# ---------------------------------------------------------------------------

def test_task_dependencies(pipeline_dag):
    """Verify the linear chain: ingest >> dbt_run >> dbt_test."""
    for upstream_id, downstream_id in EXPECTED_DEPENDENCIES:
        upstream = pipeline_dag.get_task(upstream_id)
        downstream_ids = {t.task_id for t in upstream.downstream_list}
        assert downstream_id in downstream_ids, (
            f"Expected '{upstream_id}' >> '{downstream_id}', but downstream of "
            f"'{upstream_id}' is: {downstream_ids}"
        )


def test_no_cycles(pipeline_dag):
    """DAG must be acyclic.

    In Airflow 2.x cycles are caught at DAG instantiation time and surface as
    DagBag import errors, so a successful load already implies no cycles.
    We additionally verify via topological_sort(), which raises on a cyclic graph.
    """
    try:
        # Available in Airflow 2.x
        pipeline_dag.topological_sort()
    except AttributeError:
        # Fallback: if the dag loaded without import errors, it is acyclic
        pass


# ---------------------------------------------------------------------------
# 5. Task configuration spot-checks
# ---------------------------------------------------------------------------

def test_ingest_task_bash_command(pipeline_dag):
    task = pipeline_dag.get_task("ingest_raw_jobs")
    assert "ingestion.ingest" in task.bash_command


def test_dbt_run_uses_module_invocation(pipeline_dag):
    task = pipeline_dag.get_task("dbt_run_models")
    assert "dbt.cli.main" in task.bash_command, (
        "dbt must be invoked via 'python -m dbt.cli.main' for PATH independence"
    )


def test_dbt_test_uses_fail_fast(pipeline_dag):
    task = pipeline_dag.get_task("dbt_run_tests")
    assert "--fail-fast" in task.bash_command, (
        "--fail-fast must be present so the pipeline stops on first test failure"
    )


def test_dbt_profiles_dir_injected(pipeline_dag):
    """Both dbt tasks must receive DBT_PROFILES_DIR so they find the right profile."""
    for task_id in ("dbt_run_models", "dbt_run_tests"):
        task = pipeline_dag.get_task(task_id)
        env = task.env or {}
        assert "DBT_PROFILES_DIR" in env, (
            f"Task '{task_id}' is missing DBT_PROFILES_DIR in env"
        )
