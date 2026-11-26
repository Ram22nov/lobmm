from lobmm.cli import main


def test_show_config_runs(capsys):
    assert main(["show-config"]) == 0
    assert "binance-futures" in capsys.readouterr().out
