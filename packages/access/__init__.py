"""access — Commercial access-control core (Layer A, pure).

Tier definitions, API-key hashing, monthly-quota math, and webhook rule matching
as pure functions over typed inputs. No I/O, no clock (the caller passes the
billing `period` and the `now`), so the auth/rate-limit/webhook decisions are
deterministic and test-pinned, exactly like the ranking and compliance cores.
The app layer holds the mutable stores and the HTTP wiring.
"""
