from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MetricSpec:
    name: str
    label: str
    slug: str
    definition: str
    palette: str
    aliases: tuple[str, ...] = ()
    ngram_frequency: bool = False
    mappable: bool = True


BOOK_FREQ = "book_freq"
BOOK_AVG_DEV = "book_avg_dev"
BOOK_MED_DEV = "book_med_dev"

FIC_NGRAM_TOTAL_FREQ = "fic_ngram_total_freq"
FIC_NGRAM_TOTAL_AVG_DEV = "fic_ngram_total_avg_dev"
FIC_NGRAM_TOTAL_MED_DEV = "fic_ngram_total_med_dev"
FIC_NGRAM_PREPUB_10Y_FREQ = "fic_ngram_prepub_10y_freq"
FIC_NGRAM_PREPUB_10Y_AVG_DEV = "fic_ngram_prepub_10y_avg_dev"
FIC_NGRAM_PREPUB_10Y_MED_DEV = "fic_ngram_prepub_10y_med_dev"
FIC_NGRAM_99_19_FREQ = "fic_ngram_99_19_freq"
FIC_NGRAM_99_19_AVG_DEV = "fic_ngram_99_19_avg_dev"
FIC_NGRAM_99_19_MED_DEV = "fic_ngram_99_19_med_dev"

AVG_BOOK_F = "avg_book_f"
MED_BOOK_F = "med_book_f"


METRIC_SPECS: tuple[MetricSpec, ...] = (
    MetricSpec(
        name=BOOK_FREQ,
        label="book_freq",
        slug="book_freq",
        definition=(
            "count(normalized_word) / selected frequency-basis total; the denominator "
            "is restricted to the same word_class when class discrimination is enabled"
        ),
        palette="black-white",
        aliases=("book_frequency", "frequency_total_F", "book_frequency_F"),
    ),
    MetricSpec(
        name=BOOK_AVG_DEV,
        label="book_avg_dev",
        slug="book_avg_dev",
        definition="(book_freq / avg_book_f) - 1",
        palette="red-white-blue",
        aliases=(
            "book_frequency_average_deviation",
            "book_frequency_deviation_pct",
            "book_average_deviation",
        ),
    ),
    MetricSpec(
        name=BOOK_MED_DEV,
        label="book_med_dev",
        slug="book_med_dev",
        definition="(book_freq / med_book_f) - 1",
        palette="red-white-blue",
        aliases=("book_frequency_median_deviation", "book_median_deviation"),
    ),
    MetricSpec(
        name=FIC_NGRAM_TOTAL_FREQ,
        label="fic_ngram_total_freq",
        slug="fic_ngram_total_freq",
        definition="frequency of normalized_word in all years of the fiction Ngram corpus",
        palette="black-white",
        aliases=("ngram_total_frequency", "F_Ngrams_Total", "ngram_F"),
        ngram_frequency=True,
    ),
    MetricSpec(
        name=FIC_NGRAM_TOTAL_AVG_DEV,
        label="fic_ngram_total_avg_dev",
        slug="fic_ngram_total_avg_dev",
        definition="(fic_ngram_total_freq / average fic_ngram_total_freq) - 1",
        palette="red-white-blue",
        aliases=("ngram_total_average_deviation", "Ngrams_Total_frequency_average_deviation"),
    ),
    MetricSpec(
        name=FIC_NGRAM_TOTAL_MED_DEV,
        label="fic_ngram_total_med_dev",
        slug="fic_ngram_total_med_dev",
        definition="(fic_ngram_total_freq / median fic_ngram_total_freq) - 1",
        palette="red-white-blue",
        aliases=("Ngrams_Total_frequency_median_deviation",),
    ),
    MetricSpec(
        name=FIC_NGRAM_PREPUB_10Y_FREQ,
        label="fic_ngram_prepub_10y_freq",
        slug="fic_ngram_prepub_10y_freq",
        definition=(
            "frequency of normalized_word in the fiction Ngram corpus during "
            "the ten years before publication"
        ),
        palette="black-white",
        aliases=(
            "ngram_pre_publication_10y_frequency",
            "ngram_prebublication_10y_frequency",
            "F_Ngrams_-10y",
        ),
        ngram_frequency=True,
    ),
    MetricSpec(
        name=FIC_NGRAM_PREPUB_10Y_AVG_DEV,
        label="fic_ngram_prepub_10y_avg_dev",
        slug="fic_ngram_prepub_10y_avg_dev",
        definition="(fic_ngram_prepub_10y_freq / average fic_ngram_prepub_10y_freq) - 1",
        palette="red-white-blue",
        aliases=("ngram_pre_publication_10y_average_deviation", "Ngrams_-10y_frequency_average_deviation"),
    ),
    MetricSpec(
        name=FIC_NGRAM_PREPUB_10Y_MED_DEV,
        label="fic_ngram_prepub_10y_med_dev",
        slug="fic_ngram_prepub_10y_med_dev",
        definition="(fic_ngram_prepub_10y_freq / median fic_ngram_prepub_10y_freq) - 1",
        palette="red-white-blue",
        aliases=("Ngrams_-10y_frequency_median_deviation",),
    ),
    MetricSpec(
        name=FIC_NGRAM_99_19_FREQ,
        label="fic_ngram_99_19_freq",
        slug="fic_ngram_99_19_freq",
        definition="frequency of normalized_word in the 1999-2019 fiction Ngram corpus window",
        palette="black-white",
        aliases=("ngram_recent_1999_2019_frequency", "F_Ngrams_1999-2019"),
        ngram_frequency=True,
    ),
    MetricSpec(
        name=FIC_NGRAM_99_19_AVG_DEV,
        label="fic_ngram_99_19_avg_dev",
        slug="fic_ngram_99_19_avg_dev",
        definition="(fic_ngram_99_19_freq / average fic_ngram_99_19_freq) - 1",
        palette="red-white-blue",
        aliases=(
            "ngram_recent_1999_2019_average_deviation",
            "Ngrams_1999-2019_frequency_average_deviation",
        ),
    ),
    MetricSpec(
        name=FIC_NGRAM_99_19_MED_DEV,
        label="fic_ngram_99_19_med_dev",
        slug="fic_ngram_99_19_med_dev",
        definition="(fic_ngram_99_19_freq / median fic_ngram_99_19_freq) - 1",
        palette="red-white-blue",
        aliases=("Ngrams_1999-2019_frequency_median_deviation",),
    ),
)


METRIC_BY_NAME = {spec.name: spec for spec in METRIC_SPECS}
ALIAS_TO_NAME = {
    alias: spec.name
    for spec in METRIC_SPECS
    for alias in spec.aliases
}
EXCLUDED_METRIC_NAMES = {
    "book_frequency_mad",
    "Ngrams_Total_frequency_mad",
    "Ngrams_-10y_frequency_mad",
    "Ngrams_1999-2019_mad",
    "ngram_total_mad",
    "ngram_prepub_10y_mad",
    "ngram_recent_1999_2019_mad",
    "book_to_ngram_total_frequency_deviation",
    "Negative_F_Ngram_Total_Deviation",
}

BOOK_METRIC_FIELDNAMES = [
    BOOK_FREQ,
    BOOK_AVG_DEV,
    BOOK_MED_DEV,
]

NGRAM_COLUMN_SPECS = {
    "Total": (
        FIC_NGRAM_TOTAL_FREQ,
        FIC_NGRAM_TOTAL_AVG_DEV,
        FIC_NGRAM_TOTAL_MED_DEV,
    ),
    "-10y": (
        FIC_NGRAM_PREPUB_10Y_FREQ,
        FIC_NGRAM_PREPUB_10Y_AVG_DEV,
        FIC_NGRAM_PREPUB_10Y_MED_DEV,
    ),
    "1999-2019": (
        FIC_NGRAM_99_19_FREQ,
        FIC_NGRAM_99_19_AVG_DEV,
        FIC_NGRAM_99_19_MED_DEV,
    ),
}

BOOK_NGRAM_COMPARISON_FIELDNAMES: list[str] = []

BOOK_MAP_METRICS = [
    BOOK_FREQ,
    BOOK_AVG_DEV,
    BOOK_MED_DEV,
]

NGRAM_MAP_METRICS = [
    FIC_NGRAM_TOTAL_FREQ,
    FIC_NGRAM_TOTAL_AVG_DEV,
    FIC_NGRAM_TOTAL_MED_DEV,
    FIC_NGRAM_PREPUB_10Y_FREQ,
    FIC_NGRAM_PREPUB_10Y_AVG_DEV,
    FIC_NGRAM_PREPUB_10Y_MED_DEV,
    FIC_NGRAM_99_19_FREQ,
    FIC_NGRAM_99_19_AVG_DEV,
    FIC_NGRAM_99_19_MED_DEV,
]

MAP_METRICS = [
    *BOOK_MAP_METRICS,
    *NGRAM_MAP_METRICS,
]


def is_excluded_metric(metric: str) -> bool:
    lowered = metric.lower()
    return (
        metric in EXCLUDED_METRIC_NAMES
        or "_mad" in lowered
        or lowered.endswith("mad")
        or "median_absolute_deviation" in lowered
    )


def resolve_metric_name(metric: str) -> str:
    if is_excluded_metric(metric):
        raise ValueError(
            f"Metric {metric!r} is excluded. Use signed med_dev or avg_dev "
            "when direction matters."
        )
    return ALIAS_TO_NAME.get(metric, metric)


def metric_spec(metric: str) -> MetricSpec | None:
    return METRIC_BY_NAME.get(resolve_metric_name(metric))


def metric_column_candidates(metric: str) -> tuple[str, ...]:
    canonical = resolve_metric_name(metric)
    spec = METRIC_BY_NAME.get(canonical)
    if spec is None:
        return (metric,)
    return (spec.name, *spec.aliases)


def metric_definition(metric: str) -> str:
    spec = metric_spec(metric)
    return spec.definition if spec else f"CSV column: {metric}"


def metric_label(metric: str) -> str:
    spec = metric_spec(metric)
    if spec:
        return spec.label
    return resolve_metric_name(metric).replace("_", " ").title()


def metric_slug(metric: str) -> str:
    spec = metric_spec(metric)
    if spec:
        return spec.slug
    return resolve_metric_name(metric)


def scale_slug(scale: str) -> str:
    scale = scale.lower().strip()
    if scale not in {"linear", "log"}:
        raise ValueError(f"Unsupported scale: {scale}")
    return scale


def scaled_metric_slug(metric: str, scale: str) -> str:
    return f"{metric_slug(metric)}_{scale_slug(scale)}"


def metric_palette_name(metric: str) -> str:
    spec = metric_spec(metric)
    return spec.palette if spec else "black-white"


def is_ngram_frequency_metric(metric: str) -> bool:
    spec = metric_spec(metric)
    return bool(spec and spec.ngram_frequency)


def is_current_metric(metric: str) -> bool:
    try:
        return resolve_metric_name(metric) in METRIC_BY_NAME
    except ValueError:
        return False
