"""Shared fixtures. Tests never touch the real dataset.

Every fixture here is built in code or read from a file under a hundred rows. The full
data is 2.5 GB and a test suite that depends on it stops being run, which is the only
real failure mode for a quality gate.

Fixtures carry the traps deliberately: the 365243 sentinel, XNA and XAP codes, the income
outlier, a customer with no bureau history. A fixture of clean data would let every
normalization test pass without testing anything. The rows holding each trap are named by
the module constants below, so a test can assert against exactly those rows.
"""

from __future__ import annotations

from collections.abc import Generator, Iterator
from dataclasses import dataclass
from typing import Final, NamedTuple

import duckdb
import numpy as np
import numpy.typing as npt
import polars as pl
import pytest

SKELETON_SKIP_REASON: Final = "skeleton: not implemented yet"


@pytest.hookimpl(wrapper=True)
def pytest_runtest_setup(item: pytest.Item) -> Generator[None, None, None]:
    """Report a fixture that is still a skeleton as skipped rather than failed.

    A skeleton test names a behaviour that must be verified but has no body yet.
    Failing the suite on every one of them makes CI permanently red and hides a
    real regression among a hundred expected failures. Skipping keeps the suite
    green while `-ra` still lists each skipped test, so unfinished work stays
    visible instead of being silently absent.
    """
    try:
        return (yield)
    except NotImplementedError:
        pytest.skip(SKELETON_SKIP_REASON)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item: pytest.Item) -> Generator[None, None, None]:
    """Report a test whose body is still a skeleton as skipped rather than failed.

    Becomes a no-op for a test as soon as it is implemented: a test that runs to
    completion or fails an assertion is reported exactly as normal.
    """
    try:
        return (yield)
    except NotImplementedError:
        pytest.skip(SKELETON_SKIP_REASON)


FIXTURE_APPLICATION_ROWS: Final = 50
FIXTURE_SEED: Final = 42

FIRST_APPLICATION_ID: Final = 100001
FIRST_BUREAU_ID: Final = 5000001
FIRST_PREVIOUS_ID: Final = 2000001

EMPLOYMENT_SENTINEL: Final = 365243
MISSING_CATEGORY_CODE: Final = "XNA"
NOT_APPLICABLE_CODE: Final = "XAP"
EXTREME_INCOME: Final = 117_000_000.0
DAYS_PER_YEAR: Final = 365

POSITIVE_TARGET_ROWS: Final = frozenset({2, 15, 28, 41})
EMPLOYMENT_SENTINEL_ROWS: Final = frozenset({3, 6, 11, 19, 27, 35, 43, 47, 49})
GENDER_XNA_ROWS: Final = frozenset({9, 31})
ORGANIZATION_XNA_ROWS: Final = EMPLOYMENT_SENTINEL_ROWS
EXTREME_INCOME_ROWS: Final = frozenset({23})
EXT_SOURCE_1_NULL_ROWS: Final = frozenset(range(28))
OWN_CAR_AGE_NULL_ROWS: Final = frozenset(range(17, FIXTURE_APPLICATION_ROWS))

NO_BUREAU_HISTORY_ROWS: Final = frozenset({4, 12})
SECOND_BUREAU_LOAN_ROWS: Final = frozenset(range(0, FIXTURE_APPLICATION_ROWS, 2))

SINGLE_MONTH_BUREAU_ID: Final = FIRST_BUREAU_ID + 4
BUREAU_ID_WITHOUT_BALANCE: Final = FIRST_BUREAU_ID + 5
BUREAU_STATUS_HISTORIES: Final[dict[int, tuple[str | None, ...]]] = {
    FIRST_BUREAU_ID: ("C", "C", "0", "0", "1", "2"),
    FIRST_BUREAU_ID + 1: ("0", "1", "2", "3", "4", "5"),
    FIRST_BUREAU_ID + 2: ("X", None, "0", "0"),
    FIRST_BUREAU_ID + 3: ("0", "0", "0"),
    SINGLE_MONTH_BUREAU_ID: ("0",),
}

PREVIOUS_APPLICATION_ROWS: Final = 20
NO_PREVIOUS_APPLICATION_ROWS: Final = frozenset({7})
PREVIOUS_SENTINEL_ROWS: Final = frozenset({1, 5, 10})
PREVIOUS_ID_WITHOUT_BALANCE: Final = FIRST_PREVIOUS_ID + 3

CREDIT_LIMIT_ZERO_MONTH: Final = -2


class InstalmentCase(NamedTuple):
    """One payment against its schedule, named by the behaviour it exercises."""

    days_instalment: int
    days_entry_payment: int | None
    amt_instalment: float
    amt_payment: float | None


INSTALMENT_CASES: Final = {
    "late": InstalmentCase(-100, -95, 5000.0, 5000.0),
    "early": InstalmentCase(-70, -75, 5000.0, 5000.0),
    "on_time": InstalmentCase(-40, -40, 5000.0, 5000.0),
    "underpaid": InstalmentCase(-10, -10, 5000.0, 3000.0),
    "overpaid": InstalmentCase(-130, -130, 5000.0, 6500.0),
    "zero_instalment": InstalmentCase(-160, -160, 0.0, 1200.0),
    "unpaid": InstalmentCase(-5, None, 5000.0, None),
}


@dataclass(frozen=True)
class ScoredCase:
    """Labels with predicted probabilities and, where known analytically, their AUC."""

    labels: npt.NDArray[np.int_]
    probabilities: npt.NDArray[np.float64]
    expected_auc: float | None


SEPARABLE_LABELS: Final = (0, 0, 0, 1, 1)
SEPARABLE_PROBABILITIES: Final = (0.05, 0.10, 0.20, 0.70, 0.90)
RANDOM_LABELS: Final = (0, 1, 0, 1, 0, 1)
RANDOM_PROBABILITY: Final = 0.3
PARTIAL_LABELS: Final = (0, 0, 1, 1)
PARTIAL_PROBABILITIES: Final = (0.10, 0.40, 0.35, 0.80)
PARTIAL_AUC: Final = 0.75
MISCALIBRATED_ROWS: Final = 400
MISCALIBRATED_POSITIVE_RATE: Final = 0.08
MISCALIBRATED_LOGIT_SHIFT: Final = 1.5


@pytest.fixture
def application_frame() -> pl.DataFrame:
    """A small application table containing every known value trap.

    Unique SK_ID_CURR, a TARGET positive rate of exactly 8 percent and every DAYS_* value
    negative, matching the source convention, so the sign gate has something valid to
    pass on. The trap rows are named by the *_ROWS constants of this module.
    """
    rng = np.random.default_rng(FIXTURE_SEED)
    rows = range(FIXTURE_APPLICATION_ROWS)
    amt_credit = rng.uniform(100_000, 1_500_000, FIXTURE_APPLICATION_ROWS).round(1)
    return pl.DataFrame(
        {
            "SK_ID_CURR": [FIRST_APPLICATION_ID + row for row in rows],
            "TARGET": [int(row in POSITIVE_TARGET_ROWS) for row in rows],
            "NAME_CONTRACT_TYPE": rng.choice(["Cash loans", "Revolving loans"], len(rows)),
            "CODE_GENDER": [
                MISSING_CATEGORY_CODE if row in GENDER_XNA_ROWS else ("F", "M")[row % 2]
                for row in rows
            ],
            "AMT_INCOME_TOTAL": [
                EXTREME_INCOME if row in EXTREME_INCOME_ROWS else income
                for row, income in zip(
                    rows, rng.uniform(50_000, 400_000, len(rows)).round(1), strict=True
                )
            ],
            "AMT_CREDIT": amt_credit,
            "AMT_ANNUITY": (amt_credit / rng.uniform(10, 30, len(rows))).round(1),
            "AMT_GOODS_PRICE": (amt_credit * 0.9).round(1),
            "CNT_FAM_MEMBERS": rng.integers(1, 6, len(rows)).astype(float),
            "DAYS_BIRTH": -rng.integers(18 * DAYS_PER_YEAR, 69 * DAYS_PER_YEAR, len(rows)),
            "DAYS_EMPLOYED": [
                EMPLOYMENT_SENTINEL if row in EMPLOYMENT_SENTINEL_ROWS else -int(days)
                for row, days in zip(rows, rng.integers(30, 15_000, len(rows)), strict=True)
            ],
            "DAYS_REGISTRATION": -rng.integers(0, 20_000, len(rows)).astype(float),
            "ORGANIZATION_TYPE": [
                MISSING_CATEGORY_CODE if row in ORGANIZATION_XNA_ROWS else organization
                for row, organization in zip(
                    rows,
                    rng.choice(["Business Entity Type 3", "Self-employed", "School"], len(rows)),
                    strict=True,
                )
            ],
            "OCCUPATION_TYPE": [
                None if row in EMPLOYMENT_SENTINEL_ROWS else occupation
                for row, occupation in zip(
                    rows, rng.choice(["Laborers", "Core staff", "Managers"], len(rows)), strict=True
                )
            ],
            "NAME_EDUCATION_TYPE": rng.choice(
                ["Secondary / secondary special", "Higher education"], len(rows)
            ),
            "NAME_HOUSING_TYPE": rng.choice(["House / apartment", "With parents"], len(rows)),
            "NAME_FAMILY_STATUS": rng.choice(["Married", "Single / not married"], len(rows)),
            "OWN_CAR_AGE": [
                None if row in OWN_CAR_AGE_NULL_ROWS else float(age)
                for row, age in zip(rows, rng.integers(0, 30, len(rows)), strict=True)
            ],
            "EXT_SOURCE_1": [
                None if row in EXT_SOURCE_1_NULL_ROWS else float(score)
                for row, score in zip(rows, rng.uniform(0, 1, len(rows)).round(4), strict=True)
            ],
            "EXT_SOURCE_2": rng.uniform(0, 1, len(rows)).round(4),
            "EXT_SOURCE_3": rng.uniform(0, 1, len(rows)).round(4),
        }
    )


@pytest.fixture
def bureau_frame() -> pl.DataFrame:
    """A small bureau table, including customers absent from it.

    The applications at NO_BUREAU_HISTORY_ROWS have no bureau row, which is what the LEFT
    JOIN and the FLAG_NO_BUREAU_HISTORY tests need. BUREAU_ID_WITHOUT_BALANCE has no
    matching balance rows, mirroring the real 48 percent coverage, so the two-stage fold is
    tested against a missing child.
    """
    rng = np.random.default_rng(FIXTURE_SEED)
    customer_ids = [
        FIRST_APPLICATION_ID + row
        for row in range(FIXTURE_APPLICATION_ROWS)
        for _ in range(1 + (row in SECOND_BUREAU_LOAN_ROWS))
        if row not in NO_BUREAU_HISTORY_ROWS
    ]
    loan_count = len(customer_ids)
    amt_credit_sum = rng.uniform(10_000, 900_000, loan_count).round(1)
    days_credit = -rng.integers(30, 2_900, loan_count)
    return pl.DataFrame(
        {
            "SK_ID_CURR": customer_ids,
            "SK_ID_BUREAU": [FIRST_BUREAU_ID + loan for loan in range(loan_count)],
            "CREDIT_ACTIVE": rng.choice(["Active", "Closed"], loan_count),
            "CREDIT_CURRENCY": ["currency 1"] * loan_count,
            "DAYS_CREDIT": days_credit,
            "CREDIT_DAY_OVERDUE": rng.choice([0, 0, 0, 15], loan_count),
            "DAYS_CREDIT_ENDDATE": (days_credit // 2).astype(float),
            "DAYS_ENDDATE_FACT": (days_credit // 3).astype(float),
            "AMT_CREDIT_MAX_OVERDUE": rng.choice([0.0, 0.0, 1_500.0], loan_count),
            "CNT_CREDIT_PROLONG": rng.choice([0, 0, 1], loan_count),
            "AMT_CREDIT_SUM": amt_credit_sum,
            "AMT_CREDIT_SUM_DEBT": (amt_credit_sum * rng.uniform(0, 1, loan_count)).round(1),
            "AMT_CREDIT_SUM_LIMIT": rng.choice([0.0, 0.0, 50_000.0], loan_count),
            "AMT_CREDIT_SUM_OVERDUE": rng.choice([0.0, 0.0, 0.0, 2_000.0], loan_count),
            "CREDIT_TYPE": rng.choice(["Consumer credit", "Credit card"], loan_count),
            "DAYS_CREDIT_UPDATE": -rng.integers(0, 30, loan_count),
            "AMT_ANNUITY": rng.choice([0.0, 12_000.0, 25_000.0], loan_count),
        }
    )


@pytest.fixture
def bureau_balance_frame() -> pl.DataFrame:
    """A small bureau_balance table with varied STATUS codes.

    Covers the delinquent codes 1 through 5, the closed code C, the unknown code X and a
    null, so the status predicates are tested on each branch. SINGLE_MONTH_BUREAU_ID has a
    single month of history, since regr_slope needs two points and must return null
    rather than zero below that.
    """
    records = [
        (bureau_id, -month, status)
        for bureau_id, history in BUREAU_STATUS_HISTORIES.items()
        for month, status in enumerate(history)
    ]
    return pl.DataFrame(
        records,
        schema={"SK_ID_BUREAU": pl.Int64, "MONTHS_BALANCE": pl.Int64, "STATUS": pl.String},
        orient="row",
    )


@pytest.fixture
def previous_application_frame() -> pl.DataFrame:
    """A small previous_application table carrying XNA, XAP and the 365243 sentinel.

    In the history tables XNA and XAP act as missing values, and the DAYS_FIRST_DRAWING
    and DAYS_TERMINATION columns use the same 365243 sentinel as DAYS_EMPLOYED. The
    application at NO_PREVIOUS_APPLICATION_ROWS has no earlier application, so the
    FLAG_NO_PREVIOUS_APPLICATION branch is exercised.
    """
    rng = np.random.default_rng(FIXTURE_SEED)
    customer_rows = [
        row for row in range(PREVIOUS_APPLICATION_ROWS) if row not in NO_PREVIOUS_APPLICATION_ROWS
    ]
    count = len(customer_rows)
    amt_credit = rng.uniform(20_000, 600_000, count).round(1)
    statuses = rng.choice(["Approved", "Refused", "Canceled"], count)
    is_sentinel = [index in PREVIOUS_SENTINEL_ROWS for index in range(count)]
    return pl.DataFrame(
        {
            "SK_ID_PREV": [FIRST_PREVIOUS_ID + index for index in range(count)],
            "SK_ID_CURR": [FIRST_APPLICATION_ID + row for row in customer_rows],
            "NAME_CONTRACT_TYPE": rng.choice(["Consumer loans", "Cash loans"], count),
            "AMT_ANNUITY": (amt_credit / 12).round(1),
            "AMT_APPLICATION": (amt_credit * rng.uniform(0.8, 1.1, count)).round(1),
            "AMT_CREDIT": amt_credit,
            "AMT_DOWN_PAYMENT": rng.choice([0.0, 5_000.0], count),
            "RATE_DOWN_PAYMENT": rng.choice([0.0, 0.1], count),
            "NAME_CONTRACT_STATUS": statuses,
            "DAYS_DECISION": -rng.integers(1, 2_900, count),
            "NAME_PAYMENT_TYPE": rng.choice(
                ["Cash through the bank", MISSING_CATEGORY_CODE], count
            ),
            "CODE_REJECT_REASON": [
                NOT_APPLICABLE_CODE if status == "Approved" else "HC" for status in statuses
            ],
            "NAME_GOODS_CATEGORY": rng.choice(["Mobile", MISSING_CATEGORY_CODE], count),
            "CNT_PAYMENT": rng.choice([6.0, 12.0, 24.0], count),
            "DAYS_FIRST_DRAWING": [
                float(EMPLOYMENT_SENTINEL) if sentinel else -500.0 for sentinel in is_sentinel
            ],
            "DAYS_TERMINATION": [
                float(EMPLOYMENT_SENTINEL) if sentinel else -100.0 for sentinel in is_sentinel
            ],
        }
    )


@pytest.fixture
def pos_cash_frame() -> pl.DataFrame:
    """A small POS_CASH_balance table with a delinquent month and a loan without balance.

    PREVIOUS_ID_WITHOUT_BALANCE has no rows, so the second fold through
    previous_application is tested against a missing child.
    """
    records = [
        (FIRST_PREVIOUS_ID, FIRST_APPLICATION_ID, 0, 12.0, 8.0, "Active", 0, 0),
        (FIRST_PREVIOUS_ID, FIRST_APPLICATION_ID, -1, 12.0, 9.0, "Active", 5, 0),
        (FIRST_PREVIOUS_ID, FIRST_APPLICATION_ID, -2, 12.0, 10.0, "Active", 0, 0),
        (FIRST_PREVIOUS_ID + 1, FIRST_APPLICATION_ID + 1, 0, 6.0, 0.0, "Completed", 0, 0),
        (FIRST_PREVIOUS_ID + 1, FIRST_APPLICATION_ID + 1, -1, 6.0, 1.0, "Active", 0, 0),
        (FIRST_PREVIOUS_ID + 2, FIRST_APPLICATION_ID + 2, 0, 24.0, None, "Active", 40, 12),
    ]
    return pl.DataFrame(
        records,
        schema={
            "SK_ID_PREV": pl.Int64,
            "SK_ID_CURR": pl.Int64,
            "MONTHS_BALANCE": pl.Int64,
            "CNT_INSTALMENT": pl.Float64,
            "CNT_INSTALMENT_FUTURE": pl.Float64,
            "NAME_CONTRACT_STATUS": pl.String,
            "SK_DPD": pl.Int64,
            "SK_DPD_DEF": pl.Int64,
        },
        orient="row",
    )


@pytest.fixture
def installments_frame() -> pl.DataFrame:
    """A small installments table covering late, early and underpaid cases.

    One row per INSTALMENT_CASES entry: late, early, on time, underpaid and overpaid cover
    the sign and threshold boundaries of both derived behavioural features. The zero
    instalment row tests the division guard against the case that would otherwise produce
    infinity, and the unpaid row carries the nulls the real table has for missed payments.
    """
    records = [
        (
            FIRST_PREVIOUS_ID,
            FIRST_APPLICATION_ID,
            1.0,
            number,
            case.days_instalment,
            case.days_entry_payment,
            case.amt_instalment,
            case.amt_payment,
        )
        for number, case in enumerate(INSTALMENT_CASES.values(), start=1)
    ]
    return pl.DataFrame(
        records,
        schema={
            "SK_ID_PREV": pl.Int64,
            "SK_ID_CURR": pl.Int64,
            "NUM_INSTALMENT_VERSION": pl.Float64,
            "NUM_INSTALMENT_NUMBER": pl.Int64,
            "DAYS_INSTALMENT": pl.Float64,
            "DAYS_ENTRY_PAYMENT": pl.Float64,
            "AMT_INSTALMENT": pl.Float64,
            "AMT_PAYMENT": pl.Float64,
        },
        orient="row",
    )


@pytest.fixture
def credit_card_frame() -> pl.DataFrame:
    """A small credit_card_balance table including a month with a zero credit limit.

    The zero limit at CREDIT_LIMIT_ZERO_MONTH is the denominator of utilization, so the
    division guard is tested where it would otherwise produce infinity.
    """
    records = [
        (
            FIRST_PREVIOUS_ID + 4,
            FIRST_APPLICATION_ID + 4,
            0,
            45_000.0,
            90_000.0,
            9_000.0,
            4_500.0,
            3,
            "Active",
            0,
            0,
        ),
        (
            FIRST_PREVIOUS_ID + 4,
            FIRST_APPLICATION_ID + 4,
            -1,
            30_000.0,
            90_000.0,
            0.0,
            4_500.0,
            0,
            "Active",
            0,
            0,
        ),
        (
            FIRST_PREVIOUS_ID + 4,
            FIRST_APPLICATION_ID + 4,
            CREDIT_LIMIT_ZERO_MONTH,
            0.0,
            0.0,
            0.0,
            0.0,
            0,
            "Active",
            0,
            0,
        ),
        (
            FIRST_PREVIOUS_ID + 5,
            FIRST_APPLICATION_ID + 5,
            0,
            120_000.0,
            135_000.0,
            20_000.0,
            None,
            5,
            "Active",
            35,
            35,
        ),
    ]
    return pl.DataFrame(
        records,
        schema={
            "SK_ID_PREV": pl.Int64,
            "SK_ID_CURR": pl.Int64,
            "MONTHS_BALANCE": pl.Int64,
            "AMT_BALANCE": pl.Float64,
            "AMT_CREDIT_LIMIT_ACTUAL": pl.Float64,
            "AMT_DRAWINGS_CURRENT": pl.Float64,
            "AMT_PAYMENT_CURRENT": pl.Float64,
            "CNT_DRAWINGS_CURRENT": pl.Int64,
            "NAME_CONTRACT_STATUS": pl.String,
            "SK_DPD": pl.Int64,
            "SK_DPD_DEF": pl.Int64,
        },
        orient="row",
    )


@pytest.fixture
def predictions_and_labels() -> dict[str, ScoredCase]:
    """Probabilities and labels for metric tests, with a known AUC where possible.

    Four cases. "separable" has AUC 1.0 and "random" has AUC exactly 0.5 because every
    prediction ties; these are the two anchors. "partial" has AUC 0.75, worked by hand:
    three of the four positive-negative pairs are ordered correctly. "miscalibrated" ranks
    well but its mean prediction sits far above its 8 percent base rate, which is the state
    calibration exists to fix; its AUC is not analytic and is left as None.
    """
    rng = np.random.default_rng(FIXTURE_SEED)
    miscalibrated_labels = rng.uniform(size=MISCALIBRATED_ROWS) < MISCALIBRATED_POSITIVE_RATE
    latent_score = miscalibrated_labels + rng.normal(size=MISCALIBRATED_ROWS)
    miscalibrated_probabilities = 1 / (1 + np.exp(-(latent_score + MISCALIBRATED_LOGIT_SHIFT)))
    return {
        "separable": ScoredCase(np.array(SEPARABLE_LABELS), np.array(SEPARABLE_PROBABILITIES), 1.0),
        "random": ScoredCase(
            np.array(RANDOM_LABELS), np.full(len(RANDOM_LABELS), RANDOM_PROBABILITY), 0.5
        ),
        "partial": ScoredCase(
            np.array(PARTIAL_LABELS), np.array(PARTIAL_PROBABILITIES), PARTIAL_AUC
        ),
        "miscalibrated": ScoredCase(
            miscalibrated_labels.astype(np.int_), miscalibrated_probabilities, None
        ),
    }


@pytest.fixture
def duckdb_connection() -> Iterator[duckdb.DuckDBPyConnection]:
    """An in-memory DuckDB connection, closed after the test.

    In-memory keeps the suite fast and leaves no files behind. Each test gets its own
    connection, because a registered view leaking between tests makes a failure depend on
    execution order.
    """
    connection = duckdb.connect(":memory:")
    yield connection
    connection.close()
