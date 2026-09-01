"""TruckERP document platform (Slice 0 bootstrap).

Package home for shared document **capabilities** and document **profiles**.

Slice 0 creates this boundary only. Production implementations remain in their
current modules. No caller is rewired in this slice.

Architecture lock:

- The calling business API chooses the document profile/purpose **explicitly**.
- This package must never inspect document bytes and guess DL vs Rate
  Confirmation vs Fuel vs Toll vs POD.
- A profile selects only the capabilities it needs.
- Shared capabilities do not own business posting or reconciliation.
- OpenAI transport is shared; schema, rules, prompt, and context stay
  profile-owned.
- Driver Licence does not use OpenAI. Load Lab is not this platform.
"""

__all__: list[str] = []
