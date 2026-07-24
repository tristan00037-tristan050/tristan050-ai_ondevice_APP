"""Shared helper for enumerating live route paths on a FastAPI app.

Fixture drift: fastapi 0.139.x `include_router` no longer flattens the child
router's APIRoutes into `app.routes`; it appends a single lazy
`fastapi.routing._IncludedRouter` (path=None, holding `.original_router`). Tests
that introspected `{r.path for r in app.routes}` therefore stopped seeing the
`/v1/...` paths even though the endpoints are live. Recurse into the included
routers to recover every real path. No source/registration change is involved.
"""

from __future__ import annotations


def collect_app_paths(app) -> set[str]:
    paths: set[str] = set()

    def _walk(routes) -> None:
        for route in routes or ():
            path = getattr(route, "path", None)
            if path:
                paths.add(path)
            inner = getattr(getattr(route, "original_router", None), "routes", None)
            if inner:
                _walk(inner)

    _walk(getattr(app, "routes", ()))
    return paths
