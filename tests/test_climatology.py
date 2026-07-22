# tests/test_climatology.py
"""Tests for climatology.py: day-of-water-year alignment, multi-WY loading,
percentile envelope, current-year series, and headline stats."""

from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pytest

import climatology
from timeseries import append_volumes


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_wy(cache_dir: Path, wy: int, rows: list[dict]) -> None:
    """Seed a WY{wy}_volume.parquet via append_volumes from a list of
    {date, basin, total_swe_volume_km3} dicts (optionally 'huc'; defaults to
    the 'basin' value when omitted, i.e. no name/code collision in play)."""
    by_date: dict = {}
    for row in rows:
        by_date.setdefault(row['date'], []).append(row)
    for date_str, day_rows in by_date.items():
        bands = {}
        names = {}
        for row in day_rows:
            huc = row.get('huc', row['basin'])
            names[huc] = row['basin']
            bands[huc] = pd.DataFrame({'total_swe_volume_km3': [row['total_swe_volume_km3']]})
        append_volumes(pd.Timestamp(date_str).to_pydatetime(), bands, names, cache_dir)


# ---------------------------------------------------------------------------
# day_of_water_year
# ---------------------------------------------------------------------------

class TestDayOfWaterYear:
    def test_oct1_is_day_one(self):
        assert climatology.day_of_water_year(date(2025, 10, 1)) == 1

    def test_sep30_is_day_365(self):
        assert climatology.day_of_water_year(date(2026, 9, 30)) == 365

    def test_jan1_alignment(self):
        # Oct(31)+Nov(30)+Dec(31) = 92 days, so Jan 1 is day 93.
        assert climatology.day_of_water_year(date(2026, 1, 1)) == 93

    def test_feb29_returns_none(self):
        assert climatology.day_of_water_year(date(2024, 2, 29)) is None

    def test_mar1_same_dow_in_leap_and_nonleap(self):
        # Feb always counted as 28 days -> Mar 1 aligns across years.
        leap = climatology.day_of_water_year(date(2024, 3, 1))
        nonleap = climatology.day_of_water_year(date(2026, 3, 1))
        assert leap == nonleap

    def test_accepts_timestamp_and_datetime(self):
        assert (climatology.day_of_water_year(pd.Timestamp('2025-10-01'))
                == climatology.day_of_water_year(datetime(2025, 10, 1))
                == 1)


class TestWaterDayRef:
    def test_day_one_is_oct1(self):
        ref = climatology.water_day_ref(1)
        assert (ref.month, ref.day) == (10, 1)

    def test_day_365_is_sep30(self):
        ref = climatology.water_day_ref(365)
        assert (ref.month, ref.day) == (9, 30)


# ---------------------------------------------------------------------------
# load_all_water_years
# ---------------------------------------------------------------------------

class TestLoadAllWaterYears:
    def test_empty_when_no_files(self, tmp_path):
        df = climatology.load_all_water_years(tmp_path)
        assert df.empty
        assert list(df.columns) == ['date', 'huc', 'basin', 'total_swe_volume_km3', 'wy']

    def test_concats_multiple_years_with_wy_tag(self, tmp_path):
        _write_wy(tmp_path, 2024, [{'date': '2024-01-15', 'basin': 'B', 'total_swe_volume_km3': 1.0}])
        _write_wy(tmp_path, 2025, [{'date': '2025-01-15', 'basin': 'B', 'total_swe_volume_km3': 2.0}])
        df = climatology.load_all_water_years(tmp_path)
        assert set(df['wy']) == {2024, 2025}
        assert len(df) == 2

    def test_ignores_unrelated_parquets(self, tmp_path):
        _write_wy(tmp_path, 2024, [{'date': '2024-01-15', 'basin': 'B', 'total_swe_volume_km3': 1.0}])
        (tmp_path / 'timeseries' / 'notes.parquet').write_bytes(b'garbage')
        df = climatology.load_all_water_years(tmp_path)
        assert set(df['wy']) == {2024}


# ---------------------------------------------------------------------------
# compute_climatology
# ---------------------------------------------------------------------------

class TestComputeClimatology:
    def _three_year_frame(self, tmp_path: Path) -> pd.DataFrame:
        # Same calendar day (Jan 15) across 3 historical years + 1 current year.
        for wy, vol in [(2023, 10.0), (2024, 20.0), (2025, 30.0), (2026, 99.0)]:
            bands = {'B': pd.DataFrame({'total_swe_volume_km3': [vol]})}
            append_volumes(datetime(wy, 1, 15), bands, {'B': 'B'}, tmp_path)
        return climatology.load_all_water_years(tmp_path)

    def test_excludes_current_wy(self, tmp_path):
        df = self._three_year_frame(tmp_path)
        clim = climatology.compute_climatology(df, 'B', current_wy=2026)
        row = clim[clim['dow'] == climatology.day_of_water_year(date(2026, 1, 15))].iloc[0]
        # median of [10, 20, 30] == 20; the current-year 99 must be excluded.
        assert row['p50'] == pytest.approx(20.0)
        assert row['max'] == pytest.approx(30.0)
        assert row['n'] == 3

    def test_percentiles_ordered(self, tmp_path):
        df = self._three_year_frame(tmp_path)
        clim = climatology.compute_climatology(df, 'B', current_wy=2026).iloc[0]
        assert clim['min'] <= clim['p10'] <= clim['p25'] <= clim['p50']
        assert clim['p50'] <= clim['p75'] <= clim['p90'] <= clim['max']

    def test_empty_for_unknown_basin(self, tmp_path):
        df = self._three_year_frame(tmp_path)
        assert climatology.compute_climatology(df, 'Nope', current_wy=2026).empty

    def test_empty_frame_input(self):
        empty = climatology.load_all_water_years(Path('/nonexistent'))
        assert climatology.compute_climatology(empty, 'B', current_wy=2026).empty


# ---------------------------------------------------------------------------
# current_series / n_historical_years
# ---------------------------------------------------------------------------

class TestCurrentSeries:
    def test_returns_only_current_wy(self, tmp_path):
        append_volumes(datetime(2025, 1, 15), {'B': pd.DataFrame({'total_swe_volume_km3': [5.0]})},
                       {'B': 'B'}, tmp_path)
        append_volumes(datetime(2026, 1, 15), {'B': pd.DataFrame({'total_swe_volume_km3': [7.0]})},
                       {'B': 'B'}, tmp_path)
        df = climatology.load_all_water_years(tmp_path)
        cur = climatology.current_series(df, 'B', current_wy=2026)
        assert len(cur) == 1
        assert cur.iloc[0]['total_swe_volume_km3'] == pytest.approx(7.0)

    def test_sorted_by_dow(self, tmp_path):
        append_volumes(datetime(2026, 3, 1), {'B': pd.DataFrame({'total_swe_volume_km3': [3.0]})},
                       {'B': 'B'}, tmp_path)
        append_volumes(datetime(2025, 11, 1), {'B': pd.DataFrame({'total_swe_volume_km3': [1.0]})},
                       {'B': 'B'}, tmp_path)
        df = climatology.load_all_water_years(tmp_path)
        cur = climatology.current_series(df, 'B', current_wy=2026)
        assert list(cur['dow']) == sorted(cur['dow'])


class TestNHistoricalYears:
    def test_counts_excluding_current(self, tmp_path):
        append_volumes(datetime(2023, 1, 15), {'B': pd.DataFrame({'total_swe_volume_km3': [1.0]})},
                       {'B': 'B'}, tmp_path)
        append_volumes(datetime(2024, 1, 15), {'B': pd.DataFrame({'total_swe_volume_km3': [1.0]})},
                       {'B': 'B'}, tmp_path)
        append_volumes(datetime(2026, 1, 15), {'B': pd.DataFrame({'total_swe_volume_km3': [1.0]})},
                       {'B': 'B'}, tmp_path)
        df = climatology.load_all_water_years(tmp_path)
        assert climatology.n_historical_years(df, 'B', current_wy=2026) == 2


# ---------------------------------------------------------------------------
# summarize_current
# ---------------------------------------------------------------------------

class TestSummarizeCurrent:
    def test_pct_of_median_and_rank(self, tmp_path):
        for wy, vol in [(2023, 10.0), (2024, 20.0), (2025, 30.0)]:
            append_volumes(datetime(wy, 1, 15), {'B': pd.DataFrame({'total_swe_volume_km3': [vol]})},
                           {'B': 'B'}, tmp_path)
        append_volumes(datetime(2026, 1, 15), {'B': pd.DataFrame({'total_swe_volume_km3': [20.0]})},
                       {'B': 'B'}, tmp_path)
        df = climatology.load_all_water_years(tmp_path)
        summary = climatology.summarize_current(df, 'B', current_wy=2026)
        assert summary['pct_of_median'] == pytest.approx(100.0)  # 20 vs median 20
        # Two historical years (10, 20) are < 20? No: 10 < 20 only -> rank 2.
        assert summary['rank_from_bottom'] == 2
        assert summary['total_years'] == 4

    def test_none_without_current_data(self, tmp_path):
        append_volumes(datetime(2025, 1, 15), {'B': pd.DataFrame({'total_swe_volume_km3': [1.0]})},
                       {'B': 'B'}, tmp_path)
        df = climatology.load_all_water_years(tmp_path)
        assert climatology.summarize_current(df, 'B', current_wy=2026) is None


# ---------------------------------------------------------------------------
# Dataset-aware routing
# ---------------------------------------------------------------------------

def test_load_all_water_years_swann_reads_subdir_only(tmp_path):
    import timeseries

    bands = {"17": pd.DataFrame({
        "elev_band_m": [1000], "mean_swe_mm": [100.0],
        "area_km2": [50.0], "total_swe_volume_km3": [0.005],
    })}
    names = {"17": "Columbia River Basin"}
    timeseries.append_volumes(datetime(1999, 1, 15), bands, names, tmp_path, dataset="swann")
    timeseries.append_volumes(datetime(2026, 1, 15), bands, names, tmp_path)  # snodas

    swann = climatology.load_all_water_years(tmp_path, dataset="swann")
    assert sorted(swann["wy"].unique()) == [1999]
    snodas = climatology.load_all_water_years(tmp_path)
    assert sorted(snodas["wy"].unique()) == [2026]


def test_climatology_huc_keyed_and_collision_safe(tmp_path):
    import pandas as pd
    from datetime import datetime
    import climatology
    from timeseries import append_volumes

    band = pd.DataFrame({
        "elev_band_m": [1000], "mean_swe_mm": [100.0],
        "area_km2": [50.0], "total_swe_volume_km3": [1.0],
    })
    names = {"1703": "Yakima", "170300": "Yakima"}
    for yr in (2004, 2005, 2006, 2007):
        for day in (10, 11, 12):
            bands = {"1703": band, "170300": band * 2}
            append_volumes(datetime(yr, 1, day), bands, names, tmp_path)

    df = climatology.load_all_water_years(tmp_path)
    assert "huc" in df.columns

    clim4 = climatology.compute_climatology(df, "1703", 2026)
    clim6 = climatology.compute_climatology(df, "170300", 2026)
    assert not clim4.empty and not clim6.empty
    # the two same-named basins have different volumes -> different medians
    assert clim6["p50"].iloc[0] > clim4["p50"].iloc[0]
    assert climatology.n_historical_years(df, "1703", 2026) == 4
    assert climatology.display_name(df, "1703") == "Yakima"
    assert climatology.display_name(df, "9999") == ""
