"""Lock: legacy DriverOnboardingSubmission HTTP surface is gone."""

from app.routers.driver_onboarding import router


def test_legacy_submission_routes_removed() -> None:
    paths = [getattr(route, "path", "") for route in router.routes]
    assert all("/submissions" not in path for path in paths)