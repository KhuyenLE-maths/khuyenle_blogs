from __future__ import annotations

from msx.cli import main


def test_cli_full_flow_with_fixtures(project, fixture_dir, capsys):
    root = str(project.root)

    assert main(["--root", root, "discover", "--fixtures", str(fixture_dir),
                 "--lookback-days", "3650"]) == 0
    assert "Authors that returned zero models" in capsys.readouterr().out

    assert main(["--root", root, "draft", "FixtureLab/Fixture-LM-8B"]) == 0
    assert main(["--root", root, "draft", "FixtureLab/Fixture-LM-8B"]) == 0
    assert "not overwritten" in capsys.readouterr().out

    assert main(["--root", root, "approve", "fixturelab-fixture-lm-8b"]) == 0
    assert main(["--root", root, "approve", "does-not-exist"]) == 1
    assert main(["--root", root, "build"]) == 0
    assert main(["--root", root, "status"]) == 0
    out = capsys.readouterr().out
    assert "Articles: draft 0, approved 1, published 0" in out
    assert (project.site_dir / "index.html").exists()


def test_cli_reports_missing_config(tmp_path, capsys):
    assert main(["--root", str(tmp_path), "status"]) == 1
    assert "No config.toml found" in capsys.readouterr().err
