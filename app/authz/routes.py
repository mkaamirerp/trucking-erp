"""Capability bindings for inspected routes. Not attached to FastAPI."""

from __future__ import annotations

from dataclasses import dataclass

from app.authz.catalog import CAPABILITIES
from app.authz.spec import CatalogError

_API = "/api/v1"


@dataclass(frozen=True)
class RouteBinding:
    method: str
    path: str
    module: str
    resource: str | None
    action: str | None
    kind: str
    entitlement: str | None
    note: str = ""

    @property
    def pair(self) -> tuple[str, str] | None:
        if self.resource is None:
            return None
        return (self.resource, self.action or "")


def _bind(
    method: str,
    path: str,
    module: str,
    resource: str | None,
    action: str | None,
    kind: str,
    entitlement: str | None,
    note: str = "",
) -> RouteBinding:
    if (resource is None) != (action is None):
        raise CatalogError(f"{method} {path} has a partial capability")
    if resource is not None and (resource, action) not in CAPABILITIES:
        raise CatalogError(f"{method} {path} references unknown {resource}/{action}")
    return RouteBinding(method, path, module, resource, action, kind, entitlement, note)


def _fuel(method: str, path: str, resource: str, action: str) -> RouteBinding:
    return _bind(
        method,
        f"{_API}{path}",
        "fuel",
        resource,
        action,
        "admin",
        "admin_sensitive",
        "Live gate is require_fuel_capability, which is tenant-admin only.",
    )


_FUEL_VIEW = ("fuel.providers", "view")
_FUEL_MANAGE = ("fuel.providers", "manage")
_FUEL_TEST = ("fuel.providers", "test_connection")
_FUEL_SYNC = ("fuel.providers", "sync")
_REVIEW_VIEW = ("fuel.review", "view")
_REVIEW_MANAGE = ("fuel.review", "manage")
_RECON_VIEW = ("fuel.reconciliation", "view")
_RECON_RUN = ("fuel.reconciliation", "run")

# Paths and capabilities taken from app/routers/fuel.py dependencies, not from the URL noun.
_FUEL_ROUTES: tuple[tuple[str, str, tuple[str, str]], ...] = (
    ("GET", "/fuel/providers", _FUEL_VIEW),
    ("GET", "/fuel/providers/{provider_code}", _FUEL_VIEW),
    ("GET", "/fuel/provider-connections", _FUEL_VIEW),
    ("POST", "/fuel/provider-connections", _FUEL_MANAGE),
    ("GET", "/fuel/provider-connections/{connection_id}", _FUEL_VIEW),
    ("PUT", "/fuel/provider-connections/{connection_id}", _FUEL_MANAGE),
    ("POST", "/fuel/provider-connections/{connection_id}/test", _FUEL_TEST),
    ("POST", "/fuel/provider-connections/{connection_id}/sync", _FUEL_SYNC),
    ("GET", "/fuel/dashboard/stats", _REVIEW_VIEW),
    ("GET", "/fuel/processed", _REVIEW_VIEW),
    ("GET", "/fuel/processed/{batch_id}", _REVIEW_VIEW),
    ("GET", "/fuel/review/queue", _REVIEW_VIEW),
    ("GET", "/fuel/review/batches/{batch_id}", _REVIEW_VIEW),
    ("GET", "/fuel/review/batches/{batch_id}/document", _REVIEW_VIEW),
    ("POST", "/fuel/review/batches/{batch_id}/start", _REVIEW_MANAGE),
    ("POST", "/fuel/review/batches/{batch_id}/rows/{entity_type}/{entity_id}/confirm", _REVIEW_MANAGE),
    ("POST", "/fuel/review/batches/{batch_id}/process", _REVIEW_MANAGE),
    ("GET", "/fuel/reconciliation/batches/{batch_id}", _RECON_VIEW),
    ("POST", "/fuel/reconciliation/batches/{batch_id}/run", _RECON_RUN),
    ("POST", "/fuel/bvd/imports", _REVIEW_MANAGE),
    ("GET", "/fuel/bvd/imports", _REVIEW_VIEW),
    ("GET", "/fuel/bvd/history", _REVIEW_VIEW),
    ("GET", "/fuel/bvd/imports/{import_id}/completed-basic", _REVIEW_VIEW),
    ("GET", "/fuel/bvd/imports/{import_id}/rows", _REVIEW_VIEW),
    ("GET", "/fuel/bvd/imports/{import_id}/source-reconciliation", _REVIEW_VIEW),
    ("GET", "/fuel/bvd/imports/{import_id}/summary", _REVIEW_VIEW),
    ("POST", "/fuel/bvd/imports/{import_id}/save-review", _REVIEW_MANAGE),
    ("POST", "/fuel/bvd/imports/{import_id}/process", _REVIEW_MANAGE),
    ("POST", "/fuel/bvd/imports/{import_id}/discard", _REVIEW_MANAGE),
    ("GET", "/fuel/charge-categories", _REVIEW_VIEW),
    ("GET", "/fuel/bvd/imports/{import_id}/canonical-transactions", _REVIEW_VIEW),
    ("POST", "/fuel/bvd/imports/{import_id}/classify-canonical", _REVIEW_MANAGE),
    ("PATCH", "/fuel/transactions/{transaction_id}/classification", _REVIEW_MANAGE),
    ("GET", "/fuel/bvd/imports/{import_id}/classification-summary", _REVIEW_VIEW),
    ("GET", "/fuel/bvd/imports/{import_id}/classification-unresolved-groups", _REVIEW_VIEW),
    ("POST", "/fuel/bvd/imports/{import_id}/classification-reason-group", _REVIEW_MANAGE),
    ("GET", "/fuel/bvd/imports/{import_id}/classification-audit", _REVIEW_VIEW),
    ("GET", "/fuel/nationwide/history", _REVIEW_VIEW),
    ("GET", "/fuel/nationwide/imports/{import_id}/completed-basic", _REVIEW_VIEW),
    ("POST", "/fuel/nationwide/imports", _REVIEW_MANAGE),
    ("GET", "/fuel/nationwide/imports/{import_id}/rows", _REVIEW_VIEW),
    ("GET", "/fuel/nationwide/imports/{import_id}/source-reconciliation", _REVIEW_VIEW),
    ("GET", "/fuel/nationwide/imports/{import_id}/summary", _REVIEW_VIEW),
    ("POST", "/fuel/nationwide/imports/{import_id}/save-review", _REVIEW_MANAGE),
    ("POST", "/fuel/nationwide/imports/{import_id}/process", _REVIEW_MANAGE),
    ("POST", "/fuel/nationwide/imports/{import_id}/discard", _REVIEW_MANAGE),
    ("GET", "/fuel/nationwide/imports/{import_id}/document", _REVIEW_VIEW),
    ("POST", "/fuel/manual-entry/stages", _REVIEW_MANAGE),
    ("POST", "/fuel/manual-entry/stages/receipt", _REVIEW_MANAGE),
    ("GET", "/fuel/manual-entry/stages/{stage_id}", _REVIEW_VIEW),
    ("PATCH", "/fuel/manual-entry/stages/{stage_id}", _REVIEW_MANAGE),
    ("POST", "/fuel/manual-entry/stages/{stage_id}/validate", _REVIEW_MANAGE),
    ("POST", "/fuel/manual-entry/stages/{stage_id}/process", _REVIEW_MANAGE),
    ("POST", "/fuel/manual-entry/stages/{stage_id}/discard", _REVIEW_MANAGE),
    ("GET", "/fuel/bvd/imports/{import_id}/document", _REVIEW_VIEW),
)


def _rows() -> tuple[RouteBinding, ...]:
    rows: list[RouteBinding] = [
        _bind("GET", "/healthz", "platform", None, None, "infrastructure", None),
        _bind("GET", f"{_API}/healthz", "platform", None, None, "infrastructure", None),
        _bind("GET", f"{_API}/me", "self", None, None, "self_service", None),
        _bind("PATCH", f"{_API}/me/preferences", "self", None, None, "self_service", None),
        _bind("POST", f"{_API}/auth/workspaces", "self", None, None, "self_service", None, "Creating a workspace is not an operational write."),
    ]
    rows.extend(_fuel(method, path, pair[0], pair[1]) for method, path, pair in _FUEL_ROUTES)
    rows.extend(
        (
            _bind("POST", f"{_API}/loads", "loads", "loads.records", "create", "write", None),
            _bind(
                "POST",
                f"{_API}/load-workspace-drafts",
                "loads",
                "loads.records",
                "create",
                "write",
                None,
                "Pre-promotion workspace draft only; does not create a Load row.",
            ),
            _bind(
                "GET",
                f"{_API}/load-workspace-drafts/{{draft_id}}",
                "loads",
                "loads.records",
                "view",
                "read",
                None,
            ),
            _bind(
                "PATCH",
                f"{_API}/load-workspace-drafts/{{draft_id}}",
                "loads",
                "loads.records",
                "update",
                "write",
                None,
                "CAS via expected_concurrency_version; editable only while status=draft.",
            ),
            _bind("GET", f"{_API}/loads", "loads", "loads.records", "view", "read", None),
            _bind("POST", f"{_API}/loads/parse-document", "loads", "loads.documents", "parse", "write", None, "Parsing a document is not a load create."),
            _bind("GET", f"{_API}/loads/{{load_id}}", "loads", "loads.records", "view", "read", None),
            _bind("PATCH", f"{_API}/loads/{{load_id}}", "loads", "loads.records", "update", "write", None, "status=ready on this PATCH stays rejected by the load service."),
            _bind("POST", f"{_API}/loads/{{load_id}}/confirm-document-snapshot", "loads", "loads.documents", "confirm", "write", None),
            _bind("POST", f"{_API}/loads/{{load_id}}/mark-ready", "loads", "loads.records", "mark_ready", "write", None, "Draft-to-ready rules stay in mark_load_ready."),
            _bind("GET", f"{_API}/loads/{{load_id}}/custody", "loads", "loads.custody", "view", "read", None),
            _bind("GET", f"{_API}/loads/{{load_id}}/custody-events", "loads", "loads.custody", "view", "read", None),
            _bind("GET", f"{_API}/loads/{{load_id}}/notes", "loads", "loads.notes", "view", "read", None),
            _bind("POST", f"{_API}/loads/{{load_id}}/notes", "loads", "loads.notes", "create", "write", None),
            _bind(
                "DELETE",
                f"{_API}/loads/{{load_id}}",
                "loads",
                None,
                None,
                "domain_policy_unresolved",
                None,
                "Load Integrity I5 remains unresolved. On current main an existing Load returns 409 LOAD_PHYSICAL_DELETE_TEMPORARILY_DISABLED. Casbin has no delete grant.",
            ),
            _bind("POST", f"{_API}/trips", "dispatch", "trips.records", "create", "write", None),
            _bind("POST", f"{_API}/trips/{{trip_id}}/cancel", "dispatch", "trips.records", "cancel", "write", None),
            _bind("POST", f"{_API}/trips/{{trip_id}}/complete", "dispatch", "trips.records", "complete", "write", None),
            _bind("POST", f"{_API}/trips/{{trip_id}}/loads", "dispatch", "trips.membership", "manage", "write", None),
            _bind("POST", f"{_API}/trips/{{trip_id}}/loads/{{load_id}}/remove", "dispatch", "trips.membership", "manage", "write", None),
            _bind("POST", f"{_API}/trips/{{trip_id}}/loads/{{load_id}}/activate", "dispatch", "trips.membership", "manage", "write", None),
            _bind("POST", f"{_API}/trips/{{trip_id}}/loads/{{load_id}}/complete", "dispatch", "trips.membership", "manage", "write", None),
            _bind("POST", f"{_API}/trips/{{trip_id}}/loads/{{load_id}}/accept-custody", "dispatch", "trips.custody", "transition", "write", None, "Custody rules stay in the trip service."),
            _bind("POST", f"{_API}/trips/{{trip_id}}/loads/{{load_id}}/yard-handoff", "dispatch", "trips.custody", "transition", "write", None, "Custody rules stay in the trip service."),
            _bind("POST", f"{_API}/trips/{{trip_id}}/loads/{{load_id}}/take-custody", "dispatch", "trips.custody", "transition", "write", None, "Custody rules stay in the trip service."),
            _bind("GET", f"{_API}/trips", "dispatch", "trips.records", "view", "read", None),
            _bind("GET", f"{_API}/trips/{{trip_id}}", "dispatch", "trips.records", "view", "read", None),
            _bind("PUT", f"{_API}/trips/{{trip_id}}/assignment", "dispatch", "trips.assignment", "manage", "write", None),
            _bind("PUT", f"{_API}/trips/{{trip_id}}/schedule", "dispatch", "trips.schedule", "manage", "write", None),
            _bind("POST", f"{_API}/trips/{{trip_id}}/execution-signal", "dispatch", "trips.execution", "signal", "write", None),
            _bind("GET", f"{_API}/dispatch/board", "dispatch", "dispatch.board", "view", "read", None, "Legacy board read, not operational authority."),
            _bind("GET", f"{_API}/tolls/providers", "tolls", "tolls.records", "view", "read", "admin_sensitive"),
            _bind("POST", f"{_API}/tolls/files/upload", "tolls", "tolls.imports", "manage", "write", "admin_sensitive"),
            _bind("POST", f"{_API}/tolls/files/csv", "tolls", "tolls.imports", "manage", "write", "admin_sensitive"),
            _bind("GET", f"{_API}/tolls/files", "tolls", "tolls.records", "view", "read", "admin_sensitive"),
            _bind("GET", f"{_API}/tolls/files/{{batch_id}}", "tolls", "tolls.records", "view", "read", "admin_sensitive"),
            _bind("POST", f"{_API}/tolls/files/pdf", "tolls", "tolls.imports", "manage", "write", "admin_sensitive"),
            _bind("GET", f"{_API}/tolls/pdf-reviews", "tolls", "tolls.records", "view", "read", "admin_sensitive"),
            _bind("GET", f"{_API}/tolls/pdf-reviews/{{batch_id}}", "tolls", "tolls.records", "view", "read", "admin_sensitive"),
            _bind("PATCH", f"{_API}/tolls/pdf-reviews/{{batch_id}}/rows/{{row_id}}", "tolls", "tolls.review", "manage", "write", "admin_sensitive"),
            _bind("POST", f"{_API}/tolls/pdf-reviews/{{batch_id}}/process", "tolls", "tolls.review", "manage", "write", "admin_sensitive"),
            _bind("POST", f"{_API}/tolls/manual-entry/stages", "tolls", "tolls.manual", "manage", "write", "admin_sensitive"),
            _bind("GET", f"{_API}/tolls/manual-entry/stages", "tolls", "tolls.records", "view", "read", "admin_sensitive"),
            _bind("GET", f"{_API}/tolls/manual-entry/stages/{{stage_id}}", "tolls", "tolls.records", "view", "read", "admin_sensitive"),
            _bind("PATCH", f"{_API}/tolls/manual-entry/stages/{{stage_id}}", "tolls", "tolls.manual", "manage", "write", "admin_sensitive"),
            _bind("POST", f"{_API}/tolls/manual-entry/stages/{{stage_id}}/validate", "tolls", "tolls.manual", "manage", "write", "admin_sensitive", "Validation changes stage state. It is not a read."),
            _bind("POST", f"{_API}/tolls/manual-entry/stages/{{stage_id}}/discard", "tolls", "tolls.manual", "manage", "write", "admin_sensitive"),
            _bind("POST", f"{_API}/tolls/manual-entry/stages/{{stage_id}}/process", "tolls", "tolls.manual", "manage", "write", "admin_sensitive"),
            _bind("POST", f"{_API}/payroll/pay-periods", "payroll", "payroll.periods", "open_close", "admin", "payroll"),
            _bind("GET", f"{_API}/payroll/pay-periods", "payroll", "payroll.periods", "view", "read", "payroll"),
            _bind("GET", f"{_API}/payroll/pay-periods/{{pay_period_id}}", "payroll", "payroll.periods", "view", "read", "payroll"),
            _bind("PATCH", f"{_API}/payroll/pay-periods/{{pay_period_id}}", "payroll", "payroll.periods", "update", "write", "payroll", "Live route has no require_tenant_admin."),
            _bind("POST", f"{_API}/payroll/pay-periods/{{pay_period_id}}/open", "payroll", "payroll.periods", "open_close", "admin", "payroll"),
            _bind("POST", f"{_API}/payroll/pay-periods/{{pay_period_id}}/close", "payroll", "payroll.periods", "open_close", "admin", "payroll"),
            _bind("POST", f"{_API}/payroll/pay-profiles", "payroll", "payroll.profiles", "manage", "write", "payroll"),
            _bind("GET", f"{_API}/payroll/pay-profiles", "payroll", "payroll.profiles", "view", "read", "payroll"),
            _bind("GET", f"{_API}/payroll/pay-profiles/{{profile_id}}", "payroll", "payroll.profiles", "view", "read", "payroll"),
            _bind("PATCH", f"{_API}/payroll/pay-profiles/{{profile_id}}", "payroll", "payroll.profiles", "manage", "write", "payroll"),
            _bind("POST", f"{_API}/payroll/pay-profiles/{{profile_id}}/deactivate", "payroll", "payroll.profiles", "manage", "write", "payroll"),
            _bind("POST", f"{_API}/payroll/pay-entries", "payroll", "payroll.entries", "manage", "write", "payroll"),
            _bind("GET", f"{_API}/payroll/pay-entries", "payroll", "payroll.entries", "view", "read", "payroll"),
            _bind("PATCH", f"{_API}/payroll/pay-entries/{{entry_id}}", "payroll", "payroll.entries", "manage", "write", "payroll"),
            _bind("POST", f"{_API}/payroll/pay-entries/{{entry_id}}/void", "payroll", "payroll.entries", "manage", "write", "payroll"),
            _bind("GET", f"{_API}/payroll/pay-periods/{{pay_period_id}}/summary", "payroll", "payroll.periods", "view", "read", "payroll"),
            _bind("GET", f"{_API}/payroll/pay-runs", "payroll", "payroll.runs", "view", "read", "payroll"),
            _bind("POST", f"{_API}/payroll/pay-runs", "payroll", "payroll.runs", "manage", "admin", "payroll"),
            _bind("POST", f"{_API}/payroll/pay-runs/{{run_id}}/generate", "payroll", "payroll.runs", "manage", "admin", "payroll"),
            _bind("POST", f"{_API}/payroll/pay-runs/{{run_id}}/finalize", "payroll", "payroll.runs", "manage", "admin", "payroll"),
            _bind("GET", f"{_API}/payroll/pay-runs/{{run_id}}", "payroll", "payroll.runs", "view", "read", "payroll"),
            _bind("GET", f"{_API}/payroll/pay-runs/{{run_id}}/payees", "payroll", "payroll.runs", "view", "read", "payroll"),
            _bind("GET", f"{_API}/payroll/pay-runs/{{run_id}}/items", "payroll", "payroll.runs", "view", "read", "payroll"),
            _bind("GET", f"{_API}/payroll/loads/{{load_id}}/settlement", "payroll", "payroll.settlement", "view", "read", "payroll"),
            _bind("GET", f"{_API}/payroll/documents", "payroll", "payroll.documents", "view", "read", "payroll"),
            _bind("GET", f"{_API}/payroll/documents/{{document_id}}/download", "payroll", "payroll.documents", "view", "read", "payroll"),
            _bind("GET", f"{_API}/people", "people", "people.directory", "view", "read", "admin_sensitive", "Live handler still requires tenant admin."),
            _bind("PATCH", f"{_API}/people/{{person_id}}/driver-profile", "people", "people.driver_profile", "manage", "write", "admin_sensitive", "Live handler still requires tenant admin."),
            _bind("GET", f"{_API}/people/{{person_id}}/compensation-setup", "people", "people.compensation", "view", "admin", "admin_sensitive"),
            _bind("PATCH", f"{_API}/people/{{person_id}}/compensation-setup", "people", "people.compensation", "manage", "admin", "admin_sensitive"),
            _bind("GET", f"{_API}/people/{{person_id}}/driver-role-configuration", "people", "people.role_configuration", "view", "admin", "admin_sensitive"),
            _bind("PATCH", f"{_API}/people/{{person_id}}/driver-role-configuration", "people", "people.role_configuration", "manage", "admin", "admin_sensitive"),
            _bind("GET", f"{_API}/people/{{person_id}}/audit-log", "people", "people.audit", "view", "admin", "admin_sensitive"),
            _bind("GET", f"{_API}/people/{{person_id}}", "people", "people.directory", "view", "read", "admin_sensitive", "Live handler still requires tenant admin."),
            _bind("PATCH", f"{_API}/people/{{person_id}}", "people", "people.directory", "manage", "write", "admin_sensitive"),
            _bind("GET", f"{_API}/admin/company-profile", "admin", "tenant.company", "view", "admin", "admin_sensitive"),
            _bind("PATCH", f"{_API}/admin/person-setup-ui-mode", "admin", "tenant.company", "manage", "admin", "admin_sensitive"),
            _bind("PATCH", f"{_API}/admin/doc-request-link-expiry", "admin", "tenant.company", "manage", "admin", "admin_sensitive"),
            _bind("GET", f"{_API}/admin/users", "admin", "tenant.users", "list", "read", "admin_sensitive"),
            _bind("GET", f"{_API}/admin/users/{{user_id}}/sign-in-security", "admin", "tenant.signin_security", "view", "read", "admin_sensitive"),
            _bind("POST", f"{_API}/admin/users/{{user_id}}/unlock-sign-in", "admin", "tenant.users", "unlock_sign_in", "admin", "admin_sensitive"),
            _bind("POST", f"{_API}/admin/users/invite", "admin", "tenant.users", "invite", "admin", "admin_sensitive"),
            _bind("POST", f"{_API}/admin/users/{{user_id}}/suspend", "admin", "tenant.users", "suspend", "admin", "admin_sensitive"),
            _bind("POST", f"{_API}/admin/users/{{user_id}}/reactivate", "admin", "tenant.users", "reactivate", "admin", "admin_sensitive"),
            _bind("POST", f"{_API}/admin/users/{{user_id}}/resend-invite", "admin", "tenant.users", "resend_invite", "admin", "admin_sensitive"),
            _bind("DELETE", f"{_API}/admin/users/{{user_id}}", "admin", "tenant.users", "remove", "admin", "admin_sensitive"),
            _bind("GET", f"{_API}/admin/broker-intake-settings", "admin", "tenant.broker_intake", "view", "admin", "admin_sensitive"),
            _bind("PATCH", f"{_API}/admin/broker-intake-settings", "admin", "tenant.broker_intake", "manage", "admin", "admin_sensitive"),
            _bind("POST", f"{_API}/trucks", "assets", "assets.trucks", "manage", "write", None),
            _bind("GET", f"{_API}/trucks", "assets", "assets.trucks", "view", "read", None),
            _bind("GET", f"{_API}/trucks/{{truck_id}}/suggested-trailer", "assets", "assets.trucks", "view", "read", None),
            _bind("GET", f"{_API}/trucks/{{truck_id}}", "assets", "assets.trucks", "view", "read", None),
            _bind("PATCH", f"{_API}/trucks/{{truck_id}}", "assets", "assets.trucks", "manage", "write", None),
            _bind("POST", f"{_API}/trailers", "assets", "assets.trailers", "manage", "write", None),
            _bind("GET", f"{_API}/trailers", "assets", "assets.trailers", "view", "read", None),
            _bind("GET", f"{_API}/trailers/{{trailer_id}}", "assets", "assets.trailers", "view", "read", None),
            _bind("PATCH", f"{_API}/trailers/{{trailer_id}}", "assets", "assets.trailers", "manage", "write", None),
            _bind("GET", f"{_API}/fleet", "assets", "assets.fleet", "view", "read", None),
            _bind("POST", f"{_API}/drivers", "people", "people.drivers", "manage", "write", None),
            _bind("GET", f"{_API}/drivers", "people", "people.drivers", "view", "read", None),
            _bind("GET", f"{_API}/drivers/{{driver_id}}/assignment-hints", "people", "people.drivers", "view", "read", None),
            _bind("GET", f"{_API}/drivers/{{driver_id}}", "people", "people.drivers", "view", "read", None),
            _bind("PATCH", f"{_API}/drivers/{{driver_id}}", "people", "people.drivers", "manage", "write", None),
            _bind("DELETE", f"{_API}/drivers/{{driver_id}}", "people", None, None, "not_a_grant", None, "Handler always returns 405."),
            _bind("GET", f"{_API}/drivers/{{driver_id}}/summary", "people", "people.drivers", "view", "read", None),
            _bind("POST", f"{_API}/driver-documents", "people", "people.driver_documents", "manage", "write", "driver_documents"),
            _bind("POST", f"{_API}/driver-documents/{{driver_id}}", "people", "people.driver_documents", "manage", "write", "driver_documents"),
            _bind("GET", f"{_API}/driver-documents", "people", "people.driver_documents", "view", "read", "driver_documents"),
            _bind("GET", f"{_API}/driver-documents/{{driver_id}}", "people", "people.driver_documents", "view", "read", "driver_documents"),
            _bind("POST", f"{_API}/driver-documents/{{document_id}}/deactivate", "people", "people.driver_documents", "manage", "write", "driver_documents"),
            _bind("POST", f"{_API}/driver-documents/{{document_id}}/files", "people", "people.driver_documents", "manage", "write", "driver_documents"),
            _bind("GET", f"{_API}/driver-documents/{{document_id}}/files", "people", "people.driver_documents", "view", "read", "driver_documents"),
            _bind("POST", f"{_API}/driver-documents/{{document_id}}/files/{{file_id}}/deactivate", "people", "people.driver_documents", "manage", "write", "driver_documents"),
        )
    )
    return tuple(rows)


def _index(rows: tuple[RouteBinding, ...]) -> dict[tuple[str, str], RouteBinding]:
    found: dict[tuple[str, str], RouteBinding] = {}
    for row in rows:
        key = (row.method, row.path)
        if key in found:
            raise CatalogError(f"duplicate route binding {row.method} {row.path}")
        spec = CAPABILITIES.get(row.pair) if row.pair else None
        if row.pair and spec is None:
            raise CatalogError(f"missing capability for {row.path}")
        if spec is not None:
            expected = {"admin": "admin", "operational": "write", "read": "read"}[spec.prospective]
            if row.kind != expected:
                raise CatalogError(
                    f"{row.method} {row.path} kind {row.kind} does not match {spec.prospective}"
                )
        elif row.kind not in {
            "self_service",
            "infrastructure",
            "domain_policy_unresolved",
            "not_a_grant",
        }:
            raise CatalogError(f"{row.method} {row.path} needs a capability")
        found[key] = row
    return found


ROUTE_BINDINGS = _index(_rows())


def binding_for(method: str, path: str) -> RouteBinding:
    return ROUTE_BINDINGS[(method.upper(), path)]
