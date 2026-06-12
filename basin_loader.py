from pathlib import Path
import geopandas as gpd

BASEMAP_DIR = Path(__file__).parent / "data" / "basemaps"


def load_huc2() -> gpd.GeoDataFrame:
    path = BASEMAP_DIR / "huc2_pnw.geojson"
    if not path.exists():
        raise FileNotFoundError(f"huc2_pnw.geojson not found in {BASEMAP_DIR}")
    return gpd.read_file(path).to_crs(epsg=4326)


def load_huc4() -> gpd.GeoDataFrame:
    path = BASEMAP_DIR / "huc4_pnw.geojson"
    if not path.exists():
        raise FileNotFoundError(f"huc4_pnw.geojson not found in {BASEMAP_DIR}")
    return gpd.read_file(path).to_crs(epsg=4326)
