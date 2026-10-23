from pathlib import Path

from airflow.models import DagBag

DAG_FOLDER = Path(__file__).parents[1] / "dags"
DAG_BAG = DagBag(dag_folder=str(DAG_FOLDER), include_examples=False)


def test_mubawab_detail_dag_schedule_and_limits():
    dag = DAG_BAG.get_dag("mubawab_detail_scraper")

    assert dag is not None
    assert dag.schedule == "*/15 * * * *"
    assert dag.max_active_runs == 1
    assert dag.max_active_tasks == 1
    assert dag.default_args["retries"] == 3
    assert dag.default_args["retry_delay"].total_seconds() == 5 * 60
    assert dag.default_args["retry_exponential_backoff"] is True
    assert dag.default_args["max_retry_delay"].total_seconds() == 30 * 60

    task = dag.get_task("scrape_pending_details")
    task_globals = task.python_callable.__globals__
    assert task_globals["DETAIL_LIMIT"] == 100
    assert task_globals["DETAIL_WORKERS"] == 1
