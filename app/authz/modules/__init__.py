"""Compose module catalogs. Importing this package does not load Casbin."""

from app.authz.modules.admin import CATALOG as ADMIN
from app.authz.modules.assets import CATALOG as ASSETS
from app.authz.modules.dispatch import CATALOG as DISPATCH
from app.authz.modules.fuel import CATALOG as FUEL
from app.authz.modules.loads import CATALOG as LOADS
from app.authz.modules.payroll import CATALOG as PAYROLL
from app.authz.modules.people import CATALOG as PEOPLE
from app.authz.modules.tolls import CATALOG as TOLLS
from app.authz.spec import compose

MODULES = (ADMIN, FUEL, LOADS, DISPATCH, TOLLS, PEOPLE, PAYROLL, ASSETS)
CAPABILITIES = compose(MODULES)
CAPABILITY_PAIRS = frozenset(CAPABILITIES)
