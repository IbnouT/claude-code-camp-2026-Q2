"""The package version, in one place.

The banner reads it and ``__init__`` re-exports it as ``__version__``. Kept in
its own module so importers (the REPL wiring) can read it without importing the
package root, which would be a cycle.
"""

from __future__ import annotations

__version__ = "0.11.0"
