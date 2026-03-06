from click.testing import CliRunner

from cli import main


def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "Tamper-Evident" in result.output or "Proof-of-Work" in result.output


def test_ingest_docs_help():
    runner = CliRunner()
    result = runner.invoke(main, ["ingest-docs", "--help"])
    assert result.exit_code == 0
    assert "--force" in result.output


def test_write_content_help():
    runner = CliRunner()
    result = runner.invoke(main, ["write-content", "--help"])
    assert result.exit_code == 0
    assert "--topic" in result.output
    assert "--type" in result.output


def test_run_experiment_help():
    runner = CliRunner()
    result = runner.invoke(main, ["run-experiment", "--help"])
    assert result.exit_code == 0
    assert "--name" in result.output
    assert "programmatic-seo" in result.output


def test_generate_feedback_help():
    runner = CliRunner()
    result = runner.invoke(main, ["generate-feedback", "--help"])
    assert result.exit_code == 0
    assert "--count" in result.output


def test_verify_ledger_help():
    runner = CliRunner()
    result = runner.invoke(main, ["verify-ledger", "--help"])
    assert result.exit_code == 0


def test_build_site_help():
    runner = CliRunner()
    result = runner.invoke(main, ["build-site", "--help"])
    assert result.exit_code == 0


def test_demo_run_help():
    runner = CliRunner()
    result = runner.invoke(main, ["demo-run", "--help"])
    assert result.exit_code == 0
    assert "full pipeline" in result.output.lower() or "mind-blow" in result.output.lower()
