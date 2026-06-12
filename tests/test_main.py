# tests/test_main.py
import pytest
from datetime import datetime, date
from unittest.mock import patch, MagicMock
from pathlib import Path
import main


def test_parse_args_defaults():
    args = main.parse_args([])
    assert args.date == datetime.today().date()
    assert args.band_interval == 250
    assert args.output_dir == Path('output')


def test_parse_args_custom_date():
    args = main.parse_args(['--date', '2024-04-01'])
    assert args.date == date(2024, 4, 1)


def test_parse_args_invalid_date_exits():
    with pytest.raises(SystemExit):
        main.parse_args(['--date', 'not-a-date'])


def test_parse_args_custom_band_interval():
    args = main.parse_args(['--band-interval', '500'])
    assert args.band_interval == 500


def test_parse_args_custom_output_dir():
    args = main.parse_args(['--output-dir', '/tmp/out'])
    assert args.output_dir == Path('/tmp/out')


def test_run_calls_fetch_swe(tmp_path):
    with patch('main.fetch_swe', return_value=tmp_path / 'swe.tif') as mock_fetch, \
         patch('main.get_aligned_dem', return_value=tmp_path / 'dem.tif'), \
         patch('main.load_huc2', return_value=MagicMock(geometry=[MagicMock()], iterrows=lambda: iter([]))), \
         patch('main.load_huc4', return_value=MagicMock(iterrows=lambda: iter([]))), \
         patch('main.compute_bands', return_value=MagicMock()), \
         patch('main.plot_hypsometric', return_value=[]):
        (tmp_path / 'swe.tif').touch()
        (tmp_path / 'dem.tif').touch()
        dt = datetime(2024, 4, 1)
        main.run(dt, band_interval=250, output_dir=tmp_path)
        mock_fetch.assert_called_once_with(dt)
