# SWOT rain filtering

Pipeline to flag rain-contaminated KaRIn significant wave height (SWH)
on SWOT L2 WindWave products, using GPM IMERG precipitation and a
fine-scale gradient filter (“Matu filter”).

## Method (two stages)

1. **Bulldozer filter (large scale)**  
   Match the SWOT pass mid-time to the closest IMERG half-hour granule,
   interpolate rain rate onto the SWOT grid, and mask pixels where
   IMERG rain rate exceeds a threshold (default `0.1 mm/h`).

2. **Fine-scale / gradient filter**  
   On the remaining swath, reject unphysical SWH gradients using a
   local MAD criterion (`format_ds_swot`, parameter `scale_MAD`).

Optional native SWOT quality / rain flags can be applied before or
alongside these steps.

Output fields typically written back to NetCDF:

- `IMERG_rain_rate`
- `bulldozer_mask` (0 = good, 1 = rain)
- `fine_scale_filter_mask` (0 = good, 1 = contaminated)

## Repository layout

```
swot_rain_filtering/
├── README.md
├── requirements.txt
├── pyproject.toml
├── notebooks/               # exploration & figures
├── src/swot_rain_filtering/ # reusable library
└── commands/                # launch scripts (parameters live here)
```

## Install

```bash
cd swot_rain_filtering
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

Without editable install, the CLI adds `src/` to `PYTHONPATH` automatically.
For notebooks, either `pip install -e .` or:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path("..").resolve() / "src"))  # if cwd is notebooks/
```

## Quick start

### Explore (notebook)

```bash
jupyter lab notebooks/save_IMERG_rain_rate_and_Matu_filter.ipynb
```

### Run filtering

Edit paths / thresholds inside the bash files, then, run the command:

```bash
bash commands/run_default.sh
```

Or call the Python entrypoint directly:

```bash
python commands/run_filter.py \
  --swot-root /path/to/swot \
  --output-dir /path/to/out \
  --imerg-rain-threshold 0.1 \
  --scale-MAD 5.0
```

## Main parameters

Set these in the bash launchers (or pass them to `run_filter.py`):

| Parameter | Meaning | Typical values |
|-----------|---------|----------------|
| `--imerg-rain-threshold` | Bulldozer mask if rain > threshold | `0.1` mm/h |
| `--scale-MAD` | Fine-scale gradient sensitivity | `2.5`–`7` |
| `--window-size` | Along-track MAD window | `60` |
| `--kernel-size-nan` | NaN dilation after masking | `1`–`7` |
| `--no-native-filtering` | Do not keep only `swh_karin_qual == 0` | flag |
| `--remove-rain` | Apply SWOT `rain_flag` | flag |
| `--max-files` | Maximum of files to process|
| `--inplace` | Modify files in place instead of saving them in another folder |

## Library overview

- `rain_tools` — IMERG file lookup, read, plot
- `swot_tools` — SWOT I/O, maps, `format_ds_swot`
- `pipeline` — `filter_one_pass` / `filter_directory`
- `io` — SWOT filename time parsing

## Authors / context

Original SWOT/IMERG tooling by Matu; batch IMERG + Matu
filtering workflow extended for production runs via `commands/`.

