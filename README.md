# Bookspine

Bookspine creates vocabulary-diversity visual maps from full-length plain-text books. It converts each word occurrence into a structured CSV row, calculates book-relative and corpus-relative frequency metrics, and renders those measurements as static or interactive maps.

## Features

- Convert UTF-8 `.txt` books into occurrence-level CSV files.
- Preserve word, sentence, paragraph, and chapter positions.
- Compare book frequencies with Google Books English Fiction Ngram frequencies.
- Separate functional and semantic words for class-normalized comparisons.
- Render PNG maps and pyramidal tiled BigTIFF maps.
- Explore maps and word statistics in a local browser-based viewer.
- Apply analytical or display-only smoothing without modifying source CSVs or map files.

## Requirements

- Python 3.12 or later
- Windows, macOS, or Linux for the command-line workflow
- A modern web browser for the interactive viewer

Run commands from the repository's root directory.

## Installation

Clone the repository and enter its directory:

```powershell
git clone https://github.com/gabrieldiasebraico-glitch/Bookspine.git
cd Bookspine
```

Create and activate a virtual environment on Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install "https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl"
python -m pip install -r requirements-viewer.txt
```

On macOS or Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install "https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl"
python -m pip install -r requirements-viewer.txt
```

Windows users may instead run `INSTALL_WINDOWS.bat`, followed by `run_viewer.bat`. The offline installer requires the separately distributed Python installer and wheelhouse (including spaCy, its dependencies, and the `en_core_web_sm` 3.8.0 wheel) under `installers/`; those files are not stored in this Git repository.

## Quick Start

The repository includes a small sample text for testing:

```powershell
python -m vocab_mapper.prepare_csv ".\samples\sample_book.txt" ".\output\sample_occurrences.csv"
```

Render a PNG map:

```powershell
python -m vocab_mapper.plot_visual_map ".\output\sample_occurrences.csv" ".\output\maps\sample_book_freq_linear.png" --width 2000 --metric book_freq
```

Start the interactive viewer:

```powershell
python -m vocab_mapper.viewer --port 8765 --open-browser
```

If the browser does not open automatically, visit <http://127.0.0.1:8765>.

## Preparing Occurrence CSVs

For a book stored locally:

```powershell
python -m vocab_mapper.prepare_csv ".\txt books\example.txt" ".\output\example_occurrences.csv"
```

With prepared fiction Ngram frequency tables:

```powershell
python -m vocab_mapper.prepare_csv ".\txt books\example.txt" ".\output\example_occurrences.csv" --ngram-total-csv ".\data\ngram_frequencies\eng_fiction_2019_all_ngram_frequencies.csv" --ngram-minus-10y-csv ".\data\ngram_frequencies\eng_fiction_2019_minus_10y_ngram_frequencies.csv" --ngram-1999-2019-csv ".\data\ngram_frequencies\eng_fiction_2019_recent_1999_2019_ngram_frequencies.csv"
```

Ngram tables may use `word`, `normalized_word`, or `token` as the word column and `ngram_f`, `frequency`, or `freq` as the frequency column.

## Occurrence Columns

- `word`: exact word form found in the input text.
- `normalized_word`: lowercase form, with surrounding apostrophes removed, used for counting and comparison.
- `word_number`: one-based occurrence number in the book.
- `word_class`: `functional` when all spaCy components overlapping the word have POS tags ADP, AUX, CCONJ, DET, PART, PRON, or SCONJ; otherwise `semantic`.
- `position_in_sentence`, `position_in_paragraph`, `position_in_chapter`: one-based token positions within each detected structure.
- `relative_position_in_sentence`, `relative_position_in_paragraph`, `relative_position_in_chapter`: token position divided by the detected structure's token count.
- `sentence_number`, `paragraph_number`, `chapter_number`: one-based structural location numbers.

## Metrics

### Book metrics

- `book_freq`: occurrences of a normalized word divided by the total token count for its word class. When class discrimination is disabled, all words share the book's total token count.
- `book_avg_dev`: `(book_freq / avg_book_f) - 1`.
- `book_med_dev`: `(book_freq / med_book_f) - 1`.

`avg_book_f` and `med_book_f` are calculated across **unique normalized word types within each class**, not across occurrence rows. With class discrimination enabled, Bookspine calculates separate statistics for functional and semantic word types. These parameters are written to `output\book_stats\...\*_book_stats.txt`.

### Fiction Ngram metrics

- `fic_ngram_total_freq`
- `fic_ngram_total_avg_dev`
- `fic_ngram_total_med_dev`
- `fic_ngram_prepub_10y_freq`
- `fic_ngram_prepub_10y_avg_dev`
- `fic_ngram_prepub_10y_med_dev`
- `fic_ngram_99_19_freq`
- `fic_ngram_99_19_avg_dev`
- `fic_ngram_99_19_med_dev`

The `avg_dev` metrics use `(frequency / class average) - 1`; the `med_dev` metrics use `(frequency / class median) - 1`. These class averages and medians are also calculated across unique normalized word types. Median Absolute Deviation is not used because it discards the direction of the difference.

If a required denominator is missing or zero during viewer-side recalculation, the current implementation displays a deviation of zero. Treat that value as unavailable rather than as evidence that the word exactly matches the reference statistic.

### Statistics files

Each book statistics file includes:

- Total, functional, and semantic token counts.
- Average and median book frequencies by word class.
- Minimum and maximum book frequencies by word class.
- Pre-publication fiction Ngram average and median frequencies by word class, when available.

`Ngram_Stats.txt` contains project-level fiction Ngram parameters by class.

## Class Discrimination

Function words and lexical words have very different frequency distributions. Class discrimination calculates their statistics separately to reduce that class effect. The interactive viewer's **Class norm** control switches compatible maps between class-discriminated and combined calculations.

Classification uses spaCy 3.8.16's English `en_core_web_sm` 3.8.0 model on complete sentences. ADP, AUX, CCONJ, DET, PART, PRON, and SCONJ are functional; all remaining word tags (including ADV, NUM, INTJ, and X) are semantic under the binary schema. This is a documented grouping of POS tags, not a semantic analysis. The same normalized word can occur in both classes; unique-word exports contain one row per word/class pair. Class statistics count unique words separately within each class. Ngram frequencies remain word-level and do not distinguish grammatical roles.

Bookspine preserves its original word spans and positions: contractions and hyphenated words stay as one occurrence. If spaCy splits a word into components, the occurrence is functional only when every non-punctuation component is functional. For example, a noun plus possessive particle remains semantic. Processing is local after installation; there is no automatic model download or list-based fallback. Existing CSVs retain their original classification until regenerated.

## Visual Maps

Render a single PNG map:

```powershell
python -m vocab_mapper.plot_visual_map ".\output\example_occurrences.csv" ".\output\maps\example_book_freq_linear.png" --width 2000 --metric book_freq
```

For a large book, create a pyramidal tiled compressed BigTIFF:

```powershell
python -m vocab_mapper.plot_pyramidal_tiff ".\output\example_occurrences.csv" ".\output\maps\example_book_avg_dev_linear.pyramid.ome.tif" --width 2000 --metric book_avg_dev
```

`book_freq` maps run from black at zero to white at the maximum frequency for the active scale. Signed-deviation maps use red for negative values, white for zero, and blue for positive values. Automatically generated filenames include `_linear` or `_log` before the image extension.

## Interactive Viewer

The local viewer provides:

- `/`: upload or drop a local `.txt` file, select a corpus, and choose one or more maps.
- `/viewer.html`: explore generated maps and their matching occurrence data.
- `/word-stats.html`: filter, sort, select columns, and color-scale saved or local word-metrics CSV files.

The **Smoothing** menu supports moving average, Gaussian kernel, median, Savitzky-Golay, exponential, adaptive Gaussian, structure-aware Gaussian, and display-only blur modes. Analytical smoothing operates in memory and does not modify occurrence CSVs or generated map files.

Generated source copies, occurrence CSVs, maps, and statistics are stored under `output`. Raw texts, corpus data, and generated outputs are intentionally excluded from Git.

## Batch Workflow

Process top-level `.txt` files in `txt books`:

```powershell
python -m vocab_mapper.batch
```

The command creates missing occurrence CSVs, the first `book_freq` map, word-metrics CSVs, and book-statistics files.

Render the currently configured pyramidal maps from existing occurrence CSVs:

```powershell
python .\scripts\prepare_ngram_maps.py --force
```

Write statistics files:

```powershell
python .\scripts\write_stats_files.py
```

Plot the fiction Ngram frequency density:

```powershell
python .\scripts\plot_fic_ngram_corpus_kde.py
```

The plot uses `log10(fic_ngram_total_freq)` because corpus word frequencies are highly skewed. Zero-frequency words are counted in the JSON sidecar statistics and excluded from the log-scale density curve.

## Importing Google Books Ngram Data

For the English Fiction 2019 corpus, obtain `totalcounts-1` and `1-00000-of-00001.gz` from the [Google Books Ngram exports](https://storage.googleapis.com/books/ngrams/books/20200217/eng-fiction/eng-fiction-1-ngrams_exports.html).

Build compact frequency tables for a book:

```powershell
python -m vocab_mapper.import_ngram ".\output\example_occurrences.csv" ".\data\google_ngram\eng-fiction\1-00000-of-00001.gz" ".\data\google_ngram\eng-fiction\totalcounts-1" ".\data\ngram_frequencies" --publication-year 1839
```

Review the source dataset's documentation and terms before redistributing derived corpus data. The Google Books Ngram data is not covered by Bookspine's software license.

## Methodological Limitations

- Tokenization recognizes Latin letters `A-Z` plus internal apostrophes and hyphens. It is not currently suitable for every language or writing system.
- Sentence boundaries are inferred from `.`, `!`, and `?` followed by whitespace.
- Paragraphs are inferred from blank-line separation.
- Chapters are inferred from short headings beginning with `Chapter`, `Book`, or `Part`, or from standalone Roman-numeral headings. Unusual headings may not be detected.
- POS classification is model-based and can make errors, especially on literary or unusual language. Review representative samples before relying on class comparisons.
- Google Ngram frequencies reflect the composition and limitations of the selected corpus; they should not be treated as a neutral model of language.
- Frequency-based visualizations describe textual patterns. They do not by themselves establish literary, linguistic, or causal conclusions.

## Copyright and Privacy

Only process texts that you are legally permitted to use. Public-domain status varies by country, and possessing a text does not necessarily grant permission to publish or redistribute it.

The repository excludes `txt books`, `data`, and most of `output` to reduce the risk of committing copyrighted source texts, large corpus files, or generated copies. Verify `git status` before every public push. Do not upload confidential, personal, or restricted texts to a public repository or Zenodo record.

## Citation

If you use Bookspine in research, cite the archived Zenodo release corresponding to the version you used. Zenodo supplies the final DOI and formatted citation after a GitHub release has been archived.

Until a DOI is assigned, cite the software as:

> Gabriel Dias Ebraico. (2026). *Bookspine* (Version 1.0.0) [Computer software]. GitHub. https://github.com/gabrieldiasebraico-glitch/Bookspine

Use the version-specific DOI when reproducibility requires an exact release. Use Zenodo's concept DOI when referring to Bookspine across all versions.

## License

Copyright (c) 2026 Gabriel Dias Ebraico

Bookspine is released under the [MIT License](LICENSE). Third-party datasets, book texts, and other externally sourced materials retain their own terms and are not relicensed by this repository.

The contextual classifier uses external spaCy and model packages. See [third-party notices](THIRD_PARTY_NOTICES.md) for their licenses and training-source notices.
