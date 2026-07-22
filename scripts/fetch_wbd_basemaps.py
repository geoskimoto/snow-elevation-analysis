"""One-time fetch of standard WBD basemaps for region 17 from the USGS
WBD ArcGIS REST service. Writes data/basemaps/huc4_pnw.geojson (12
subregions) and data/basemaps/huc6_pnw.geojson (22 basins). Committed for
reproducibility; not part of any scheduled job.

Usage: venv/bin/python scripts/fetch_wbd_basemaps.py
"""
import sys
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://hydro.nationalmap.gov/arcgis/rest/services/wbd/MapServer"
OUT = Path(__file__).resolve().parent.parent / "data" / "basemaps"
# (layer id, code field, where clause, output filename, expected count)
LAYERS = [
    (2, "huc4", "huc4 LIKE '17%'", "huc4_pnw.geojson", 12),
    (3, "huc6", "huc6 LIKE '17%'", "huc6_pnw.geojson", 22),
]


def fetch(layer: int, field: str, where: str) -> bytes:
    params = urllib.parse.urlencode({
        "where": where,
        "outFields": f"{field},name,areasqkm,states",
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "geojson",
    })
    url = f"{BASE}/{layer}/query?{params}"
    with urllib.request.urlopen(url, timeout=300) as resp:
        return resp.read()


def main() -> None:
    import geopandas as gpd
    for layer, field, where, filename, expected in LAYERS:
        raw = fetch(layer, field, where)
        path = OUT / filename
        path.write_bytes(raw)
        g = gpd.read_file(path)
        if len(g) != expected:
            print(f"ERROR: {filename}: got {len(g)} features, expected {expected}",
                  file=sys.stderr)
            sys.exit(1)
        if not g.geometry.is_valid.all():
            print(f"ERROR: {filename}: invalid geometries", file=sys.stderr)
            sys.exit(1)
        print(f"{filename}: {len(g)} features OK")


if __name__ == "__main__":
    main()
