# Rain Tools # 
# by Matu ####

import xarray as xr
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
from pathlib import Path

import cartopy.crs as ccrs
import cartopy.feature as cfeature


from matplotlib.colors import ListedColormap, BoundaryNorm
from matplotlib.colors import to_hex

#test

# ##################
# font properties #
# ##################

import matplotlib.font_manager as fm
# Regular and bold font paths
font_regular_path = "../.fonts/times/times.ttf"
font_bold_path = "../.fonts/times/timesbd.ttf"  # Bold
# Register both fonts
fm.fontManager.addfont(font_regular_path)
fm.fontManager.addfont(font_bold_path)
# Create font properties
font_regular = fm.FontProperties(fname=font_regular_path)
font_bold = fm.FontProperties(fname=font_bold_path)
# Set default font to regular Times New Roman
plt.rcParams['font.family'] = font_regular.get_name()


# ── IMERG ─────────────────────────────────────────────────────────────────────
IMERG_ROOT = Path("/home/datawork-cersat-project/pimep/data/imerg/gpm_3imerghhl/v7b")
IMERG_VARS = ["precipitation"]  # add "randomError" if needed


# #################
# IMERG Colormap #
# #################

imerg_colors = [
    (1, 1, 1, 0),
    (0.076, 0.206, 0.112),
    (0.000, 0.490, 0.162),
    (0.000, 0.591, 0.236),
    (0.235, 0.740, 0.060),
    (0.603, 0.839, 0.000),
    (0.893, 0.893, 0.000),
    (0.941, 0.695, 0.000),
    (0.942, 0.386, 0.000),
    (0.855, 0.000, 0.000),
    (0.374, 0.060, 0.066)
]


imerg_levels = [0, 0.1, 0.2, 0.3, 0.5, 1, 2, 3, 5, 10, 20, 50]
imerg_cmap = ListedColormap(imerg_colors)
imerg_norm = BoundaryNorm(imerg_levels, imerg_cmap.N)

imerg_palette = [to_hex(c) for c in imerg_colors]



# -- FUNCTIONS -----------------------------------------------------------------

# ── IMERG file-finder ─────────────────────────────────────────────────────────

def imerg_closest(t_mid: pd.Timestamp, imerg_root=IMERG_ROOT):
    """
    Return the IMERG file whose start time is closest to t_mid.

    IMERG granules start every 30 minutes:
        00:00, 00:30, 01:00, ...

    Returns
    -------
    Path or None
        Path to the closest IMERG file, or None if it cannot be found.
    """
    mins_since_midnight = t_mid.hour * 60 + t_mid.minute + t_mid.second / 60

    # Nearest 30-minute slot
    slot = ((int(mins_since_midnight) + 15) // 30) * 30

    date = t_mid.normalize()
    if slot >= 1440:
        slot -= 1440
        date += pd.Timedelta(days=1)

    hh, mm = divmod(slot, 60)
    day_dir = imerg_root / date.strftime("%Y") / date.strftime("%j")

    pattern = (
        f"3B-HHR-L.MS.MRG.3IMERG."
        f"{date.strftime('%Y%m%d')}-S{hh:02d}{mm:02d}00-E"
        f"*.{slot:04d}.V07*.RT-H5"
    )

    hits = sorted(day_dir.glob(pattern)) if day_dir.is_dir() else []

    if not hits:
        print(f"day_dir: {day_dir}\n hh: {hh} - mm: {mm}")
        return None

    return hits[0]

# ── IMERG 2 closests (bracket) file-finder ─────────────────────────────────────────────────────────


def imerg_bracket(t_mid: pd.Timestamp, imerg_root=IMERG_ROOT):
    """
    Return (path_before, path_after, weight_after) for linear interpolation
    of IMERG precipitation at t_mid.

    IMERG granules are 30-min wide: 00:00-00:29, 00:30-00:59, …
    The 4-digit field in the filename is minutes-since-midnight of the
    granule start.

    weight_after = fraction of the 30-min window elapsed at t_mid (0–1)

    Returns (None, None, None) if either file is missing.
    """
    mins_since_midnight = t_mid.hour * 60 + t_mid.minute

    # Floor to the current 30-minute slot
    slot_b = (mins_since_midnight // 30) * 30
    slot_a = slot_b + 30

    date_b = t_mid.normalize()
    date_a = date_b + pd.Timedelta("1D") if slot_a >= 1440 else date_b
    slot_a = slot_a % 1440

    def _find(date, slot):
        hh, mm = divmod(slot, 60)

        day_dir = (
            imerg_root
            / date.strftime("%Y")
            / date.strftime("%j")
        )

        pattern = (
            f"3B-HHR-L.MS.MRG.3IMERG."
            f"{date.strftime('%Y%m%d')}-S{hh:02d}{mm:02d}00-E"
            f"*.{slot:04d}.V07*.RT-H5"
        )

        hits = sorted(day_dir.glob(pattern)) if day_dir.is_dir() else []

        if not hits:
            print(f"day_dir: {day_dir}\n hh: {hh} - mm: {mm}")

        return hits[0] if hits else None

    f_b = _find(date_b, slot_b)
    f_a = _find(date_a, slot_a)

    if f_b is None or f_a is None:
        return None, None, None

    t_b = date_b + pd.Timedelta(minutes=slot_b)
    w_a = (t_mid - t_b).total_seconds() / 1800.0  # 1800 s = 30 min

    return f_b, f_a, float(np.clip(w_a, 0.0, 1.0))

# ── IMERG reader ──────────────────────────────────────────────────────────────

def read_imerg_precip(imerg_path: Path,
                      lon_min=-180, lon_max=180, lat_min=-90, lat_max=90) -> tuple:
    """
    Open one IMERG HDF5 granule (group='Grid'), slice to bbox.
    Returns (precip_2d, lon_1d, lat_1d)  with precip_2d shaped (lat, lon).
    Fill values (< 0) are set to NaN.

    Note: IMERG dims are (time, lon, lat) — lon comes before lat!
    """
    with xr.open_dataset(imerg_path, group="Grid", engine="netcdf4") as ds:
        ds_bb = ds.sel(lon=slice(lon_min, lon_max), lat=slice(lat_min, lat_max))
        # precipitation: (time=1, lon, lat) → squeeze → (lon, lat) → transpose → (lat, lon)
        precip = ds_bb["precipitation"].values.squeeze()   # (lon, lat)
        precip = precip.T.copy()                            # (lat, lon), C-contiguous
        precip[precip < 0] = np.nan                        # mask fill values
        lon_vals = ds_bb["lon"].values
        lat_vals = ds_bb["lat"].values
    return precip, lon_vals, lat_vals


print("IMERG helpers defined: imerg_bracket(), read_imerg_precip()")


def plot_imerg_rain(ds, fig=None, ax=None, vmin=0.1, vmax=50, figsize=(10, 10), shrink=0.8, cmap=imerg_cmap, norm=imerg_norm, levels = imerg_levels):
    """
    Plot JMA radar rain rate on a Mercator map.
    """

    rain = ds["precipitation"]#.transpose("lat", "lon")
    # Mask tiny values
    #rain = rain.where(rain >= 0)

    lons, lats = ds.lon.values, ds.lat.values
    #lats = ds.lat

    if fig is None:
        fig = plt.figure(figsize=figsize, constrained_layout=True)
    if ax is None:
        ax = plt.axes(projection=ccrs.Mercator())

    mesh = ax.pcolormesh(lons, lats, rain, transform=ccrs.PlateCarree(), shading="auto", cmap=cmap, norm=norm)

    ax.coastlines(resolution="50m", linewidth=0.8)
    ax.add_feature(cfeature.BORDERS, linewidth=0.5)
    ax.add_feature(cfeature.LAND, zorder=0, alpha=0.2)
    #ax.set_extent([float(lons.min()), float(lons.max()), float(lats.min()), float(lats.max())], crs=ccrs.PlateCarree())
    gl = ax.gridlines(draw_labels=True, linewidth=0.4, color="gray", alpha=0.5, linestyle="--")
    gl.top_labels = gl.right_labels = False



    cbar = plt.colorbar(mesh, ax=ax, pad=0.02, shrink=shrink, ticks=levels)
    cbar.set_label("IMERG Rain rate [mm.h$^{-1}$]")

    return fig, ax









