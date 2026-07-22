# Bookspine Vocabulary Maps Portable

This zip contains the local Bookspine Vocabulary Maps application, the Windows Python installer, and offline Python dependency wheels.

## Windows Setup

1. Extract the zip to a folder with enough free disk space.
2. Run `INSTALL_WINDOWS.bat`.
3. Run `run_viewer.bat`.
4. Optional: run `CREATE_DESKTOP_SHORTCUT.bat`.

The setup script installs Python 3.12 for the current Windows user only when Python 3.12 is not already available. It then creates a local `.venv` folder inside the extracted package and installs the bundled wheels without downloading from the internet.

If the browser does not open automatically, open:

```text
http://127.0.0.1:8765
```

## Included Data

- Application source in `vocab_mapper`.
- Browser UI in `vocab_mapper\web_viewer`.
- Derived occurrence CSVs, map JSON metadata, book stats, word metrics, and plot exports under `output`.
- Ngram frequency CSVs under `data\ngram_frequencies` for upload-based map generation.
- Python installer in `installers`.
- Offline dependency wheels in `installers\wheelhouse`.

Large rendered TIFF map files, raw Google Ngram source files, caches, virtual environments, and source book text folders are not included.

## Sharing Note

Occurrence CSVs contain word sequences derived from books. Check distribution permissions before sharing the package outside your research group.
