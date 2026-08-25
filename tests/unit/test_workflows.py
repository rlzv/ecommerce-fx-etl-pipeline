from pathlib import Path


def test_daily_and_monitor_workflows_have_required_controls() -> None:
    workflows = Path(__file__).resolve().parents[2] / ".github" / "workflows"
    daily = (workflows / "daily-pipeline.yml").read_text(encoding="utf-8")
    monitor = (workflows / "freshness-monitor.yml").read_text(encoding="utf-8")

    assert 'cron: "15 6 * * *"' in daily
    assert "workflow_dispatch:" in daily
    assert "cancel-in-progress: false" in daily
    assert "secrets.DATABASE_URL" in daily
    assert "secrets.ORDERS_API_KEY" in daily
    assert "ecommerce-etl run-pipeline" in daily

    assert 'cron: "0 7 * * *"' in monitor
    assert "workflow_run:" in monitor
    assert "github.event.workflow_run.conclusion != 'success'" in monitor
    assert "ecommerce-etl check-freshness --max-age-hours 26" in monitor
