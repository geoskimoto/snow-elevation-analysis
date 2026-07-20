# tests/test_timeseries.py
"""Tests for timeseries.py: water_year, append_volumes, load_timeseries."""

from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

import timeseries


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_bands_df(swe_mm: float = 100.0, area_km2: float = 10.0) -> pd.DataFrame:
    """Return a minimal elevation-bands DataFrame matching compute_bands() output."""
    return pd.DataFrame({
        'elev_band_m': [500, 750],
        'mean_swe_mm': [swe_mm, swe_mm * 1.5],
        'area_km2': [area_km2, area_km2],
        'total_swe_volume_km3': [
            swe_mm * area_km2 * 1e-6,
            swe_mm * 1.5 * area_km2 * 1e-6,
        ],
    })


def _expected_volume(swe_mm: float = 100.0, area_km2: float = 10.0) -> float:
    """Sum of total_swe_volume_km3 across both bands in _make_bands_df."""
    return swe_mm * area_km2 * 1e-6 + swe_mm * 1.5 * area_km2 * 1e-6


# ---------------------------------------------------------------------------
# water_year
# ---------------------------------------------------------------------------

class TestWaterYear:
    def test_oct1_starts_new_water_year(self):
        assert timeseries.water_year(datetime(2025, 10, 1)) == 2026

    def test_sep30_is_previous_water_year(self):
        assert timeseries.water_year(datetime(2025, 9, 30)) == 2025

    def test_jan_mid_year(self):
        assert timeseries.water_year(datetime(2026, 1, 15)) == 2026

    def test_july_mid_year(self):
        assert timeseries.water_year(datetime(2025, 7, 4)) == 2025

    def test_oct31_is_new_water_year(self):
        assert timeseries.water_year(datetime(2025, 10, 31)) == 2026

    def test_nov1_is_new_water_year(self):
        assert timeseries.water_year(datetime(2025, 11, 1)) == 2026

    def test_sep1_is_same_calendar_year(self):
        assert timeseries.water_year(datetime(2026, 9, 1)) == 2026

    def test_returns_int(self):
        result = timeseries.water_year(datetime(2025, 10, 1))
        assert isinstance(result, int)


# ---------------------------------------------------------------------------
# load_timeseries — missing file
# ---------------------------------------------------------------------------

class TestLoadTimeseriesMissingFile:
    def test_returns_empty_dataframe_when_file_missing(self, tmp_path):
        df = timeseries.load_timeseries(wy=2026, cache_dir=tmp_path)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0

    def test_empty_df_has_correct_columns(self, tmp_path):
        df = timeseries.load_timeseries(wy=2026, cache_dir=tmp_path)
        assert list(df.columns) == ['date', 'basin', 'total_swe_volume_km3']

    def test_date_column_dtype_is_datetime(self, tmp_path):
        df = timeseries.load_timeseries(wy=2026, cache_dir=tmp_path)
        # Empty frame still needs the declared dtype
        assert df.dtypes['date'] == 'datetime64[ns]'

    def test_missing_wy_file_does_not_create_file(self, tmp_path):
        timeseries.load_timeseries(wy=2026, cache_dir=tmp_path)
        expected = tmp_path / 'timeseries' / 'WY2026_volume.parquet'
        assert not expected.exists()


# ---------------------------------------------------------------------------
# append_volumes + load_timeseries integration
# ---------------------------------------------------------------------------

class TestAppendVolumes:
    def test_creates_parquet_on_first_call(self, tmp_path):
        date = datetime(2026, 1, 15)
        bands_by_basin = {'Columbia River Basin': _make_bands_df()}
        timeseries.append_volumes(date, bands_by_basin, tmp_path)
        expected = tmp_path / 'timeseries' / 'WY2026_volume.parquet'
        assert expected.exists()

    def test_correct_volume_value(self, tmp_path):
        date = datetime(2026, 1, 15)
        bands_by_basin = {'Columbia River Basin': _make_bands_df()}
        timeseries.append_volumes(date, bands_by_basin, tmp_path)
        df = timeseries.load_timeseries(wy=2026, cache_dir=tmp_path)
        row = df[df['basin'] == 'Columbia River Basin'].iloc[0]
        assert row['total_swe_volume_km3'] == pytest.approx(_expected_volume())

    def test_idempotent_same_date_same_basin(self, tmp_path):
        date = datetime(2026, 1, 15)
        bands_by_basin = {'Columbia River Basin': _make_bands_df()}
        timeseries.append_volumes(date, bands_by_basin, tmp_path)
        timeseries.append_volumes(date, bands_by_basin, tmp_path)
        df = timeseries.load_timeseries(wy=2026, cache_dir=tmp_path)
        rows = df[(df['basin'] == 'Columbia River Basin') &
                  (df['date'] == pd.Timestamp(date))]
        assert len(rows) == 1

    def test_multiple_basins_stored(self, tmp_path):
        date = datetime(2026, 1, 15)
        bands_by_basin = {
            'Columbia River Basin': _make_bands_df(swe_mm=100.0),
            'Upper Columbia': _make_bands_df(swe_mm=50.0),
            'Snake': _make_bands_df(swe_mm=75.0),
        }
        timeseries.append_volumes(date, bands_by_basin, tmp_path)
        df = timeseries.load_timeseries(wy=2026, cache_dir=tmp_path)
        assert set(df['basin']) == {'Columbia River Basin', 'Upper Columbia', 'Snake'}

    def test_multiple_dates_accumulate(self, tmp_path):
        bands_by_basin = {'Columbia River Basin': _make_bands_df()}
        for day in [1, 8, 15]:
            timeseries.append_volumes(datetime(2026, 1, day), bands_by_basin, tmp_path)
        df = timeseries.load_timeseries(wy=2026, cache_dir=tmp_path)
        assert len(df) == 3

    def test_volume_summed_across_all_bands(self, tmp_path):
        """total_swe_volume_km3 stored must equal sum of all bands, not per-band value."""
        date = datetime(2026, 2, 1)
        # Two bands: 100mm * 10km2 * 1e-6 + 150mm * 10km2 * 1e-6
        bands = _make_bands_df(swe_mm=100.0, area_km2=10.0)
        timeseries.append_volumes(date, {'TestBasin': bands}, tmp_path)
        df = timeseries.load_timeseries(wy=2026, cache_dir=tmp_path)
        row = df[df['basin'] == 'TestBasin'].iloc[0]
        expected = (100.0 * 10.0 + 150.0 * 10.0) * 1e-6
        assert row['total_swe_volume_km3'] == pytest.approx(expected)

    def test_date_stored_as_datetime(self, tmp_path):
        date = datetime(2026, 3, 1)
        timeseries.append_volumes(date, {'Columbia River Basin': _make_bands_df()}, tmp_path)
        df = timeseries.load_timeseries(wy=2026, cache_dir=tmp_path)
        assert pd.api.types.is_datetime64_any_dtype(df['date'])

    def test_different_water_years_use_separate_files(self, tmp_path):
        bands_by_basin = {'Columbia River Basin': _make_bands_df()}
        # WY2025: date in Jan 2025
        timeseries.append_volumes(datetime(2025, 1, 15), bands_by_basin, tmp_path)
        # WY2026: date in Jan 2026
        timeseries.append_volumes(datetime(2026, 1, 15), bands_by_basin, tmp_path)
        wy2025 = tmp_path / 'timeseries' / 'WY2025_volume.parquet'
        wy2026 = tmp_path / 'timeseries' / 'WY2026_volume.parquet'
        assert wy2025.exists()
        assert wy2026.exists()
        df25 = timeseries.load_timeseries(wy=2025, cache_dir=tmp_path)
        df26 = timeseries.load_timeseries(wy=2026, cache_dir=tmp_path)
        assert len(df25) == 1
        assert len(df26) == 1

    def test_idempotent_does_not_change_volume(self, tmp_path):
        """Calling append_volumes twice with same date must not alter stored volume."""
        date = datetime(2026, 4, 1)
        bands_by_basin = {'Columbia River Basin': _make_bands_df(swe_mm=200.0)}
        timeseries.append_volumes(date, bands_by_basin, tmp_path)
        timeseries.append_volumes(date, bands_by_basin, tmp_path)
        df = timeseries.load_timeseries(wy=2026, cache_dir=tmp_path)
        row = df[df['basin'] == 'Columbia River Basin'].iloc[0]
        assert row['total_swe_volume_km3'] == pytest.approx(_expected_volume(swe_mm=200.0))

    def test_huc2_and_huc4_stored_together(self, tmp_path):
        """HUC2 and HUC4 basins all go into the same parquet file."""
        date = datetime(2026, 1, 15)
        bands_by_basin = {
            'Columbia River Basin': _make_bands_df(),   # HUC2
            'Upper Columbia': _make_bands_df(),          # HUC4
            'Snake': _make_bands_df(),                   # HUC4
        }
        timeseries.append_volumes(date, bands_by_basin, tmp_path)
        df = timeseries.load_timeseries(wy=2026, cache_dir=tmp_path)
        # All three in the same file
        assert len(df) == 3
        parquet_path = tmp_path / 'timeseries' / 'WY2026_volume.parquet'
        assert parquet_path.exists()
        # Only one file was created
        other_parquet = list((tmp_path / 'timeseries').glob('*.parquet'))
        assert len(other_parquet) == 1


# ---------------------------------------------------------------------------
# load_timeseries — file exists
# ---------------------------------------------------------------------------

class TestLoadTimeseriesFileExists:
    def test_returns_correct_columns(self, tmp_path):
        date = datetime(2026, 1, 15)
        timeseries.append_volumes(date, {'Columbia River Basin': _make_bands_df()}, tmp_path)
        df = timeseries.load_timeseries(wy=2026, cache_dir=tmp_path)
        assert list(df.columns) == ['date', 'basin', 'total_swe_volume_km3']

    def test_returns_dataframe(self, tmp_path):
        date = datetime(2026, 1, 15)
        timeseries.append_volumes(date, {'Columbia River Basin': _make_bands_df()}, tmp_path)
        df = timeseries.load_timeseries(wy=2026, cache_dir=tmp_path)
        assert isinstance(df, pd.DataFrame)

    def test_basin_column_is_string(self, tmp_path):
        date = datetime(2026, 1, 15)
        timeseries.append_volumes(date, {'Columbia River Basin': _make_bands_df()}, tmp_path)
        df = timeseries.load_timeseries(wy=2026, cache_dir=tmp_path)
        # pandas >= 2.0 may return StringDtype rather than object; check semantic type
        assert pd.api.types.is_string_dtype(df['basin'])

    def test_volume_column_is_float(self, tmp_path):
        date = datetime(2026, 1, 15)
        timeseries.append_volumes(date, {'Columbia River Basin': _make_bands_df()}, tmp_path)
        df = timeseries.load_timeseries(wy=2026, cache_dir=tmp_path)
        assert pd.api.types.is_float_dtype(df['total_swe_volume_km3'])


# ---------------------------------------------------------------------------
# load_timeseries ordering
# ---------------------------------------------------------------------------

class TestLoadTimeseriesOrdering:
    """Rows are appended in run order, so an out-of-order backfill must still
    load chronologically -- charts plot rows in array order."""

    def test_backfilled_date_loads_chronologically(self, tmp_path):
        # Analyze March first, then backfill January (the reported scenario).
        for day in (datetime(2026, 3, 1), datetime(2026, 1, 15)):
            timeseries.append_volumes(day, {'Columbia River Basin': _make_bands_df()}, tmp_path)

        df = timeseries.load_timeseries(wy=2026, cache_dir=tmp_path)

        assert list(df['date']) == [pd.Timestamp('2026-01-15'), pd.Timestamp('2026-03-01')]

    def test_each_basin_is_chronological(self, tmp_path):
        bands = _make_bands_df()
        for day in (datetime(2026, 3, 1), datetime(2026, 1, 15), datetime(2026, 2, 1)):
            timeseries.append_volumes(
                day,
                {'Columbia River Basin': bands, 'Yakima': bands},
                tmp_path,
            )

        df = timeseries.load_timeseries(wy=2026, cache_dir=tmp_path)

        for basin in ('Columbia River Basin', 'Yakima'):
            dates = df[df['basin'] == basin]['date']
            assert dates.is_monotonic_increasing, f'{basin} rows are not chronological'

    def test_index_is_contiguous_after_sort(self, tmp_path):
        for day in (datetime(2026, 3, 1), datetime(2026, 1, 15)):
            timeseries.append_volumes(day, {'Columbia River Basin': _make_bands_df()}, tmp_path)

        df = timeseries.load_timeseries(wy=2026, cache_dir=tmp_path)

        assert list(df.index) == [0, 1]


# ---------------------------------------------------------------------------
# Dataset-aware routing
# ---------------------------------------------------------------------------

def test_append_and_load_swann_dataset_routes_to_subdir(tmp_path):
    date = datetime(2026, 1, 15)
    bands = {"Columbia River Basin": pd.DataFrame({
        "elev_band_m": [1000], "mean_swe_mm": [100.0],
        "area_km2": [50.0], "total_swe_volume_km3": [0.005],
    })}
    timeseries.append_volumes(date, bands, tmp_path, dataset="swann")

    assert (tmp_path / "timeseries" / "swann" / "WY2026_volume.parquet").exists()
    # default (snodas) tree untouched
    assert not (tmp_path / "timeseries" / "WY2026_volume.parquet").exists()

    df = timeseries.load_timeseries(2026, tmp_path, dataset="swann")
    assert len(df) == 1
    assert timeseries.load_timeseries(2026, tmp_path).empty          # snodas view is empty
