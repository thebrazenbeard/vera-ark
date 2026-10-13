import json

from vera_ark import cli


def test_cli_explicit_physics_guard_synthetic_demo(tmp_path, capsys):
    config = {
        "schema": "VERA_ARK_PHYSICA_GUARD_CONFIG_V1",
        "position_m": [0.0, 0.0], "x_axis": [2.0, 0.0],
        "y_axis": [0.0, 2.0], "radius_m": 0.1,
        "obstacles": [{"id": "wall", "lower": [0.9, -0.2], "upper": [1.1, 0.2]}],
    }
    p = tmp_path/"model.json"
    p.write_text(json.dumps(config), encoding="utf-8-sig")
    assert cli.main(["demo","--steps","1","--log-dir",str(tmp_path/"logs"),
                     "--motion-guard-config",str(p)]) == 0
    assert "release_recorded" in capsys.readouterr().out


def test_cli_rejects_bad_config_before_any_session(tmp_path):
    p = tmp_path/"bad.json"
    p.write_text('{"schema":"wrong","obstacles":[]}')
    assert cli.main(["demo", "--steps", "1", "--log-dir",str(tmp_path/"logs"),
                  "--motion-guard-config",str(p)]) == 2
    assert not (tmp_path/"logs").exists()
