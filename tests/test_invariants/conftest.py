"""Hypothesis settings profiles for the invariant battery.

Two profiles, selected via the ``HYPOTHESIS_PROFILE`` env var (default: ``ci``):

* ``ci``      — the fast, deterministic gate profile (few examples, seeded).
* ``explore`` — the heavy on-demand run (many examples).

``deadline=None`` is required: building a 30-host op through the REST ``TestClient``
per example easily exceeds Hypothesis's 200 ms default deadline. The battery also
drives the function-scoped ``db_session``/``client`` fixtures across examples (each
test creates a fresh op per example in its body), so the ``function_scoped_fixture``
health check is suppressed by design.
"""
import os

from hypothesis import HealthCheck, settings

_COMMON = dict(
    deadline=None,
    suppress_health_check=[
        HealthCheck.function_scoped_fixture,
        HealthCheck.too_slow,
    ],
)

settings.register_profile("ci", max_examples=25, derandomize=True, **_COMMON)
settings.register_profile("explore", max_examples=500, **_COMMON)
settings.load_profile(os.getenv("HYPOTHESIS_PROFILE", "ci"))
