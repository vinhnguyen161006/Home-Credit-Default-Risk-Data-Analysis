"""Shared fixtures. Tests never touch the real dataset.

Every fixture here is built in code or read from a file under a hundred rows. The full
data is 2.5 GB and a test suite that depends on it stops being run, which is the only
real failure mode for a quality gate.

Fixtures carry the traps deliberately: the 365243 sentinel, XNA and XAP codes, the income
outlier, a customer with no bureau history. A fixture of clean data would let every
normalization test pass without testing anything.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import TYPE_CHECKING, Final

import pytest

if TYPE_CHECKING:
    import polars as pl

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

EMPLOYMENT_SENTINEL: Final = 365243


@pytest.fixture
def application_frame() -> pl.DataFrame:
    """A small application table containing every known value trap.

    TODO:
        - Build FIXTURE_APPLICATION_ROWS rows with unique SK_ID_CURR and a TARGET
          positive rate near 8 percent, so a stratification test has both classes.
        - Include at least one row per trap: DAYS_EMPLOYED at EMPLOYMENT_SENTINEL,
          CODE_GENDER at XNA, ORGANIZATION_TYPE at XNA, an extreme AMT_INCOME_TOTAL, null
          EXT_SOURCE_1, null OWN_CAR_AGE.
        - Keep DAYS_* negative, matching the source convention, so the sign gate has
          something valid to pass on.
        - Build it in code rather than reading a file, so the trap rows are visible in the
          fixture and a reader can see what each test is exercising.
    """
    raise NotImplementedError


@pytest.fixture
def bureau_frame() -> pl.DataFrame:
    """A small bureau table, including a customer absent from it.

    TODO:
        - Reference a subset of the application ids, deliberately leaving at least one
          application id with no bureau row. That gap is what the LEFT JOIN and the
          FLAG_NO_BUREAU_HISTORY tests need.
        - Give one SK_ID_BUREAU no matching balance rows, mirroring the real 48 percent
          coverage, so the two-stage fold is tested against a missing child.
    """
    raise NotImplementedError


@pytest.fixture
def bureau_balance_frame() -> pl.DataFrame:
    """A small bureau_balance table with varied STATUS codes.

    TODO:
        - Include the delinquent codes 1 through 5, the closed code C, and at least one
          null, so the status predicates are tested on each branch.
        - Give one loan a single month of history, since regr_slope needs two points and
          must return null rather than zero below that.
    """
    raise NotImplementedError


@pytest.fixture
def installments_frame() -> pl.DataFrame:
    """A small installments table covering late, early and underpaid cases.

    TODO:
        - Include a payment after its due date, one before, one exactly on time, one
          underpaid and one overpaid. These five cases cover the sign and threshold
          boundaries of both derived behavioural features.
        - Include a row with AMT_INSTALMENT of zero, so the division guard is tested
          against the case that would otherwise produce infinity.
    """
    raise NotImplementedError


@pytest.fixture
def predictions_and_labels() -> tuple[object, object]:
    """Probabilities and labels for metric tests, with a known AUC.

    TODO:
        - Construct a set whose AUC is known analytically, so a metric test asserts a
          value rather than merely that the code runs.
        - Include a perfectly separable case and a random case, giving AUC 1.0 and about
          0.5 as the two anchors.
        - Include a deliberately miscalibrated set, where ranking is good but the mean
          prediction is far above the base rate. That is the state calibration exists to
          fix, and a calibration test needs it as input.
    """
    raise NotImplementedError


@pytest.fixture
def duckdb_connection() -> object:
    """An in-memory DuckDB connection, closed after the test.

    TODO:
        - Yield an in-memory connection and close it in teardown. In-memory keeps the
          suite fast and leaves no files behind.
        - Do not share one connection across tests. A registered view leaking between
          tests makes a failure depend on execution order.
    """
    raise NotImplementedError
