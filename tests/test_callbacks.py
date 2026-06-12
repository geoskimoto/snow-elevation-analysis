import io
import zipfile
from pathlib import Path
from unittest.mock import patch, MagicMock
import plotly.graph_objects as go
import pytest


def test_make_download_zip_with_two_files(tmp_path):
    from callbacks import _make_download_zip
    huc2 = tmp_path / 'snow_hypsometric_huc2_20240401.png'
    huc4 = tmp_path / 'snow_hypsometric_huc4_20240401.png'
    huc2.write_bytes(b'PNG2')
    huc4.write_bytes(b'PNG4')
    result = _make_download_zip(huc2, huc4)
    assert result['filename'] == 'snow_hypsometric.zip'
    assert result['base64'] is True
    import base64
    raw = base64.b64decode(result['content'])
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        names = zf.namelist()
    assert huc2.name in names
    assert huc4.name in names


def test_make_download_zip_skips_missing_files(tmp_path):
    from callbacks import _make_download_zip
    huc2 = tmp_path / 'missing_huc2.png'
    huc4 = tmp_path / 'missing_huc4.png'
    result = _make_download_zip(huc2, huc4)
    import base64
    raw = base64.b64decode(result['content'])
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        assert len(zf.namelist()) == 0


def test_make_download_zip_partial_files(tmp_path):
    from callbacks import _make_download_zip
    huc2 = tmp_path / 'huc2.png'
    huc2.write_bytes(b'data')
    huc4 = tmp_path / 'missing.png'
    result = _make_download_zip(huc2, huc4)
    import base64
    raw = base64.b64decode(result['content'])
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        assert zf.namelist() == ['huc2.png']
