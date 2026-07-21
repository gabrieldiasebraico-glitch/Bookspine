from __future__ import annotations

from pathlib import Path

import dask.array as da
import napari
import tifffile
import zarr


TIFF_PATH = Path(
    r"C:\Users\User\Documents\New project\output\maps\lord_of_the_rings_book_avg_dev_linear.pyramid.ome.tif"
)


def lazy_levels():
    print("Opening TIFF as Zarr-backed pyramid...", flush=True)
    tif = tifffile.TiffFile(TIFF_PATH)
    store = tif.aszarr(series=0)
    group = zarr.open(store, mode="r")
    arrays = [da.from_zarr(group[str(index)]) for index in range(len(tif.series[0].levels))]
    print(f"Prepared {len(arrays)} lazy levels.", flush=True)
    return tif, arrays


print("Reading TIFF metadata...", flush=True)
with tifffile.TiffFile(TIFF_PATH) as tif:
    level_count = len(tif.series[0].levels)
    base_shape = tif.series[0].levels[0].shape

open_tif, pyramid = lazy_levels()
print("Creating napari viewer...", flush=True)
viewer = napari.Viewer(title=f"{TIFF_PATH.name} ({base_shape[1]} x {base_shape[0]}, {level_count} levels)")
print("Adding image layer...", flush=True)
viewer.add_image(
    pyramid,
    name=TIFF_PATH.stem,
    multiscale=True,
    rgb=True,
)
viewer.window.show()
viewer.window._qt_window.show()
viewer.window._qt_window.raise_()
viewer.window._qt_window.activateWindow()
print("Starting napari event loop.", flush=True)
try:
    napari.run()
finally:
    open_tif.close()
