"""
Small, explicit pytest helpers.

Keep modules narrow: only wiring that mirrors production (tenant on Request, DB URLs) — not alternate
business rules. If a test needs different behavior, override in that test file and document why.
"""
