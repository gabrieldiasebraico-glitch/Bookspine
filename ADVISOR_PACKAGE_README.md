# Vocabulary Map Viewer Portable Package

This package contains the interactive vocabulary map viewer and the generated data needed to browse the maps.

## Run

From this folder:

```powershell
.\run_viewer.bat
```

On macOS or Linux:

```sh
sh ./run_viewer.sh
```

If the browser does not open automatically, open:

```text
http://127.0.0.1:8765
```

The viewer uses only the Python standard library. No `pip install` step is required for viewing.

## What Is Included

- Interactive viewer source code in `vocab_mapper`.
- Generated occurrence CSVs in `output\CSV Ocurrence Maps`.
- Map metadata in `output\maps`.
- Book statistics in `output\book_stats`.
- Supporting plot exports in `output\plots`, when present.

The large rendered `.tif` / `.tiff` map images, raw Ngram data, virtual environments, caches, and source book text files are intentionally excluded. The browser viewer reconstructs the visible map rows directly from the CSVs and metadata, so the large TIFF files are not required for interactive viewing.

## Viewer Scale

- `Fit` compresses the whole selected map into the available screen height.
- `1 px` restores the default row scale: one word occurrence row is one screen pixel high.
- Zooming out does not drop rows from the selected visible range. When too many rows are visible to draw individually, the viewer groups neighboring rows into screen bins and draws the average color for each bin. Individual word labels appear only when rows are large enough to inspect directly.
- The narrow bar at the far right is an overview navigator. Click or drag it to jump through the book.
- The top-right information panel reports bibliographic metadata when available, word counts, class ratios, and metric-specific statistics for the selected map.

## Sharing Note

Occurrence CSVs contain the word sequence for each included book. Check distribution permissions before sharing CSVs derived from copyrighted texts outside your research group.
