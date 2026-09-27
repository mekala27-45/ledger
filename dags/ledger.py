"""The ledger pipeline as an Airflow DAG, in the Makefile's order.

Each task runs one make target, so the DAG and a local ``make pipeline`` run exactly
the same commands. tests/pipeline/test_dag_order.py reads this file without Airflow
and fails if its order and the Makefile's disagree. The fetch of the real public
datasets is outside the DAG: it is run by hand, recorded in data/PROVENANCE.md, and
its files are content hashed, so a scheduled run never silently changes its inputs.
"""

from __future__ import annotations

from datetime import datetime

STAGES = [
    "generate",
    "ingest",
    "contracts",
    "warehouse",
    "reconcile",
    "metrics",
    "models",
    "functions",
    "manifest",
    "render",
    "export",
    "site-data",
]

try:  # Airflow is optional: the order is testable without it.
    from airflow import DAG
    from airflow.operators.bash import BashOperator
except ImportError:  # pragma: no cover - exercised only where Airflow is installed
    DAG = None

if DAG is not None:  # pragma: no cover
    with DAG(
        dag_id="ledger",
        description="Generate, stage, build, reconcile, model, render and export Harborline's analytics",
        start_date=datetime(2026, 9, 1),
        schedule=None,
        catchup=False,
        tags=["ledger"],
    ) as dag:
        previous = None
        for stage in STAGES:
            task = BashOperator(
                task_id=stage.replace("-", "_"),
                bash_command=f"cd {{{{ var.value.ledger_root }}}} && make {stage}",
            )
            if previous is not None:
                previous >> task
            previous = task
