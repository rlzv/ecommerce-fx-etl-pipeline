from pathlib import Path


def test_required_project_documentation_exists() -> None:
    root = Path(__file__).resolve().parents[2]
    required_files = [
        root / "README.md",
        root / "docs" / "project-writeup.md",
        root / "docs" / "architecture.md",
        root / "docs" / "data-quality.md",
        root / "docs" / "monitoring.md",
        root / "docs" / "ai-usage.md",
    ]

    assert all(path.is_file() for path in required_files)


def test_writeup_covers_assignment_topics() -> None:
    root = Path(__file__).resolve().parents[2]
    writeup = (root / "docs" / "project-writeup.md").read_text(encoding="utf-8")

    required_topics = [
        "## Data issues and decisions",
        "## Production monitoring",
        "## AI usage",
        "implausible_unit_price_outlier",
        "silently misses the daily trigger",
        "No AI service is used by the runtime ETL pipeline",
    ]

    for topic in required_topics:
        assert topic in writeup


def test_readme_contains_results_and_document_links() -> None:
    root = Path(__file__).resolve().parents[2]
    readme = (root / "README.md").read_text(encoding="utf-8")

    required_content = [
        "## Results",
        "## Architecture",
        "## Cleaning decisions",
        "## Automation and monitoring",
        "docs/project-writeup.md",
        "docs/ai-usage.md",
    ]

    for content in required_content:
        assert content in readme
