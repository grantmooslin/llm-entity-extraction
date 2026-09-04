# Test package marker.
#
# Monorepo: the editable `mailroom` install exposes its own src/tests as a
# top-level regular `tests` package, which would otherwise shadow this
# directory's PEP-420 namespace. Making this a regular package too lets the
# `from tests.test_langfuse_tracing import ...` imports resolve via the
# sys.path entry inserted in conftest.py (this package root wins by order).
