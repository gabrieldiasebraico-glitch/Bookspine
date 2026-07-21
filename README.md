# Vocabulary Diversity Visual Maps

This project prepares word-occurrence CSV files from full-book `.txt` files. Each CSV row is one occurrence of one word, preserving location in the book and attaching frequency/deviation metrics for visual maps.

## Prepare Occurrence CSVs

```powershell
python -m vocab_mapper.prepare_csv ".\books\example.txt" ".\output\example_occurrences.csv"
```

With fiction Ngram frequency data:

```powershell
python -m vocab_mapper.prepare_csv ".\books\example.txt" ".\output\example_occurrences.csv" --ngram-total-csv ".\data\ngram_frequencies\eng_fiction_2019_all_ngram_frequencies.csv" --ngram-minus-10y-csv ".\data\ngram_frequencies\eng_fiction_2019_minus_10y_ngram_frequencies.csv" --ngram-1999-2019-csv ".\data\ngram_frequencies\eng_fiction_2019_recent_1999_2019_ngram_frequencies.csv"
```

Ngram CSVs may use `word`, `normalized_word`, or `token` for the word column, and `ngram_f`, `frequency`, or `freq` for the frequency column.

## Core Columns

- `word`: exact word form found in the book.
- `normalized_word`: lowercase form used for counting and comparison.
- `word_number`: occurrence number in the full book.
- `word_class`: `functional` or `semantic`.
- `position_in_sentence`, `position_in_paragraph`, `position_in_chapter`: absolute positions inside each structure.
- `relative_position_in_sentence`, `relative_position_in_paragraph`, `relative_position_in_chapter`: relative positions inside each structure.
- `sentence_number`, `paragraph_number`, `chapter_number`: structural location numbers.

## Book Metrics

- `book_freq`: word occurrences divided by the total word count for that word class. With class discrimination on, functional and semantic words have separate denominators. Without class discrimination, all words share one denominator.
- `book_avg_dev`: `(book_freq / avg_book_f) - 1`, where `avg_book_f` is calculated within the active class-discrimination mode.
- `book_med_dev`: `(book_freq / med_book_f) - 1`, where `med_book_f` is calculated within the active class-discrimination mode.

`avg_book_f` and `med_book_f` are book-level parameters, not map metrics. They are written to `output\book_stats\...\*_book_stats.txt`.

## Fiction Ngram Metrics

- `fic_ngram_total_freq`
- `fic_ngram_total_avg_dev`
- `fic_ngram_total_med_dev`
- `fic_ngram_prepub_10y_freq`
- `fic_ngram_prepub_10y_avg_dev`
- `fic_ngram_prepub_10y_med_dev`
- `fic_ngram_99_19_freq`
- `fic_ngram_99_19_avg_dev`
- `fic_ngram_99_19_med_dev`

The `avg_dev` metrics use `(frequency / class average) - 1`. The `med_dev` metrics use `(frequency / class median) - 1`. Median Absolute Deviation (`*_mad`) is intentionally excluded because it removes the sign of the difference.

## Parameters

Each book stats file includes:

- `total_words`
- `total_functional_words`
- `total_semantic_words`
- `avg_book_f` and `med_book_f` for each class
- `functional_max_book_f`, `functional_min_book_f`
- `semantic_max_book_f`, `semantic_min_book_f`
- `fic_ngram_prepub_10y_freq_avg` and `fic_ngram_prepub_10y_freq_med` for each class when pre-publication data is present

`Ngram_Stats.txt` includes project-level fiction Ngram parameters by class:

- `fic_ngrams_total_freq_avg`
- `fic_ngrams_total_freq_med`
- `fic_ngram_99_19_freq_avg`
- `fic_ngrams_99_19_freq_med`

## Class Discrimination

Class discrimination separates functional and semantic words before calculating frequencies and deviations. This reduces the class effect caused by function words and lexical words having very different occurrence patterns. The interactive viewer has a `Class norm` checkbox to switch the selected map between class-discriminated and no-class-discrimination values.

## Visual Maps

Render a single map:

```powershell
python -m vocab_mapper.plot_visual_map ".\output\the_fall_of_the_house_of_usher_occurrences.csv" ".\output\maps\usher_book_freq_linear.png" --width 2000 --metric book_freq
```

For large books, use pyramidal tiled compressed BigTIFF:

```powershell
python -m vocab_mapper.plot_pyramidal_tiff ".\output\lord_of_the_rings_occurrences.csv" ".\output\maps\lord_of_the_rings_book_avg_dev_linear.pyramid.ome.tif" --width 2000 --metric book_avg_dev
```

`book_freq` maps are black at 0 and white at the maximum `book_freq` for the active class scale. Signed deviation maps use red-white-blue: red is negative, white is zero, and blue is positive.
Automatically generated map filenames end with `_linear` or `_log` before the image extension so both scale variants can coexist.

## Interactive Viewer

```powershell
python -m vocab_mapper.viewer --port 8765
```

Open:

```text
http://127.0.0.1:8765
```

Pages:

- `/` uploads or drops a local `.txt` file, selects the corpus, and selects one or more maps from a multi-select menu.
- `/viewer.html` scans `output\maps`, resolves matching occurrence CSVs, hides excluded historical metrics, and groups maps by canonical book and metric.
- `/word-stats.html` loads saved word metrics CSVs or a local CSV for filtering, sorting, column selection, and color scaling.

Generated source copies, occurrence CSVs, map files, and stats are written under `output\source_texts`, `output\CSV Ocurrence Maps\generated`, `output\maps\generated`, and `output\book_stats`.

## Batch Workflow

```powershell
python -m vocab_mapper.batch
```

The batch command creates missing occurrence CSVs, the first `book_freq` map, and `book_stats` files for top-level `.txt` files in `txt books`.

Render all current pyramidal maps from existing occurrence CSVs:

```powershell
python .\scripts\prepare_ngram_maps.py --force
```

Write stats files:

```powershell
python .\scripts\write_stats_files.py
```

Plot the fiction Ngram corpus frequency density:

```powershell
python .\scripts\plot_fic_ngram_corpus_kde.py
```

This writes `output\plots\fic_ngram_total_freq_corpus_kde.png` and a JSON sidecar. The KDE is calculated over `log10(fic_ngram_total_freq)` because corpus word frequencies are highly skewed; zero-frequency words are counted in the sidecar stats and excluded from the log-scale density curve.

## Importing Google Ngram Frequencies

For English Fiction 2019, download `totalcounts-1` and `1-00000-of-00001.gz` from:

```text
https://storage.googleapis.com/books/ngrams/books/20200217/eng-fiction/eng-fiction-1-ngrams_exports.html
```

Build compact Ngram CSVs for a book:

```powershell
python -m vocab_mapper.import_ngram ".\output\the_fall_of_the_house_of_usher_occurrences.csv" ".\data\google_ngram\eng-fiction\1-00000-of-00001.gz" ".\data\google_ngram\eng-fiction\totalcounts-1" ".\data\ngram_frequencies" --publication-year 1839
```
