from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
import rasterio.mask
from shapely.geometry import mapping


def compute_bands(
    swe_tif: Path,
    dem_tif: Path,
    basin_geom,
    band_interval_m: int = 250,
    min_band_area_km2: float = 0.0,
) -> pd.DataFrame:
    geom_json = [mapping(basin_geom)]

    with rasterio.open(swe_tif) as src:
        swe_arr, _ = rasterio.mask.mask(src, geom_json, crop=True, nodata=-9999)
        swe_arr = swe_arr[0].astype(np.float32)
        res_deg = abs(src.transform.a)
        lat_mid = (src.bounds.top + src.bounds.bottom) / 2.0

    with rasterio.open(dem_tif) as src:
        dem_arr, _ = rasterio.mask.mask(src, geom_json, crop=True, nodata=-9999.0)
        dem_arr = dem_arr[0].astype(np.float32)

    # Tolerate ≤1 pixel crop difference from rasterio.mask.mask; raise on larger mismatch
    if abs(swe_arr.shape[0] - dem_arr.shape[0]) > 1 or abs(swe_arr.shape[1] - dem_arr.shape[1]) > 1:
        raise ValueError(
            f"DEM/SWE grid mismatch: SWE shape {swe_arr.shape} vs DEM shape {dem_arr.shape}. "
            "Ensure the DEM was built with get_aligned_dem() using the same SNODAS tif."
        )
    min_h = min(swe_arr.shape[0], dem_arr.shape[0])
    min_w = min(swe_arr.shape[1], dem_arr.shape[1])
    swe_arr = swe_arr[:min_h, :min_w]
    dem_arr = dem_arr[:min_h, :min_w]

    # SNODAS uses -9999 and 32767 (int16 max) as nodata; values above 5000mm are artifacts
    valid_mask = (swe_arr != -9999) & (swe_arr <= 5000) & (~np.isnan(swe_arr)) & (dem_arr != -9999) & (~np.isnan(dem_arr))
    swe_valid = swe_arr[valid_mask]
    elev_valid = dem_arr[valid_mask]

    # Pixel area in km² (approximate; latitude-corrected)
    km_per_deg_lon = 111.32 * np.cos(np.radians(lat_mid))
    km_per_deg_lat = 111.32
    pixel_km2 = res_deg * km_per_deg_lon * res_deg * km_per_deg_lat

    if len(elev_valid) == 0:
        return pd.DataFrame(columns=['elev_band_m', 'mean_swe_mm', 'area_km2', 'total_swe_volume_km3'])



    elev_min = int(np.floor(elev_valid.min() / band_interval_m) * band_interval_m)
    elev_max = int(np.ceil(elev_valid.max() / band_interval_m) * band_interval_m)

    records = []
    for band_floor in range(elev_min, elev_max, band_interval_m):
        band_ceil = band_floor + band_interval_m
        in_band = (elev_valid >= band_floor) & (elev_valid < band_ceil)
        n_pixels = int(in_band.sum())
        if n_pixels == 0:
            continue
        area_km2 = n_pixels * pixel_km2
        if area_km2 < min_band_area_km2:
            continue
        mean_swe = float(swe_valid[in_band].mean())
        records.append({
            'elev_band_m': band_floor,
            'mean_swe_mm': mean_swe,
            'area_km2': area_km2,
            'total_swe_volume_km3': mean_swe * area_km2 * 1e-6,
        })

    return pd.DataFrame(records)
