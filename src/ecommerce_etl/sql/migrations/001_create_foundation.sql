CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS reference;
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS quarantine;
CREATE SCHEMA IF NOT EXISTS mart;
CREATE SCHEMA IF NOT EXISTS ops;

CREATE TABLE IF NOT EXISTS ops.pipeline_runs (
    pipeline_run_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pipeline_name TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    metrics JSONB NOT NULL DEFAULT '{}'::JSONB,
    error_message TEXT,
    CONSTRAINT pipeline_runs_status_check
        CHECK (status IN ('running', 'succeeded', 'failed')),
    CONSTRAINT pipeline_runs_finished_at_check
        CHECK (finished_at IS NULL OR finished_at >= started_at)
);

CREATE INDEX IF NOT EXISTS pipeline_runs_name_started_at_idx
    ON ops.pipeline_runs (pipeline_name, started_at DESC);

CREATE TABLE IF NOT EXISTS ops.data_quality_results (
    data_quality_result_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pipeline_run_id BIGINT REFERENCES ops.pipeline_runs (pipeline_run_id),
    check_name TEXT NOT NULL,
    check_status TEXT NOT NULL,
    observed_value NUMERIC,
    expected_value TEXT,
    details JSONB NOT NULL DEFAULT '{}'::JSONB,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT data_quality_results_status_check
        CHECK (check_status IN ('passed', 'warning', 'failed'))
);

CREATE INDEX IF NOT EXISTS data_quality_results_run_id_idx
    ON ops.data_quality_results (pipeline_run_id);
