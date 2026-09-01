"""Document profiles (Slice 0 bootstrap).

A profile is chosen explicitly by a calling business API. It declares which
shared capabilities it needs and owns its schema, rules, prompt, and output
mapping.

Shipped compositions today live in existing modules (Driver Licence capture /
OpenCV / PDF417; Rate Confirmation parse-document). Fuel, Toll, and POD are
future profiles only — not implemented here.

This package must not inspect bytes to guess which profile to run.
"""

__all__: list[str] = []
