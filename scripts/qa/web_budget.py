#!/usr/bin/env python3
"""Page weight budget for the built site (W6, arquitectura-agentes.md F4.7).

    "$PY" scripts/qa/web_budget.py            # the heaviest pages against their budget (needs web/dist)
    "$PY" scripts/qa/web_budget.py --update   # lower the budgets to what pages weigh now (never raises)
    "$PY" scripts/qa/web_budget.py --add web/dist/cas/x/index.html --reason "…"   # budget a new heavy page

meta/qa/web_budget.json holds a ratchet: each budgeted page can only get lighter. The heavy pages
embed every intervention in their island props (intervencions 2.8 MB, mapa 1.4 MB, without the full
texts since issue #97), so a budget grows with the number of interventions, plus 1 % tolerance;
anything else that grows fails W6.
After an optimisation, --update locks the gain in.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qa.checks.web import BUDGET_FILE, DIST, allowed, html_sizes, n_interventions  # noqa: E402
from qa.model import REPO_ROOT, Context  # noqa: E402

TOP = 10


def initial(sizes: dict[str, int], n: int) -> dict:
    heavy = sorted(sizes, key=lambda p: -sizes[p])
    return {
        "updated": date.today().isoformat(),
        "interventions": n,
        "tolerance": 0.01,
        "pages": {p: sizes[p] for p in heavy[:TOP]},
        "max_other_page": sizes[heavy[TOP]] if len(heavy) > TOP else 0,
        "total_html": sum(sizes.values()),
    }


def tightened(budget: dict, sizes: dict[str, int], n: int) -> tuple[dict, list[str]]:
    """Rebase the budget on today's intervention count and lower every limit a page now beats."""
    scale = max(1.0, n / budget["interventions"])
    new = dict(budget, interventions=max(n, budget["interventions"]), updated=date.today().isoformat())
    changes = []

    def lower(name: str, old: int, now: int | None) -> int:
        limit = int(old * scale)
        if now is not None and now < limit:
            changes.append(f"{name}: {limit / 1e6:.2f} → {now / 1e6:.2f} MB")
            return now
        return limit
    new["pages"] = {p: lower(p, b, sizes.get(p)) for p, b in budget["pages"].items()}
    others = [s for p, s in sizes.items() if p not in budget["pages"]]
    new["max_other_page"] = lower("max_other_page", budget["max_other_page"], max(others, default=None))
    new["total_html"] = lower("total_html", budget["total_html"], sum(sizes.values()))
    return new, changes


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--update", action="store_true", help="lower the budgets to the current weights")
    ap.add_argument("--add", metavar="PAGE", help="give a page its own budget at its current weight")
    ap.add_argument("--reason", help="why --add is needed (goes in the commit, not the file)")
    args = ap.parse_args(argv)

    ctx = Context(REPO_ROOT / "data")
    dist = REPO_ROOT / DIST
    if not (dist / "cas/index.html").exists():
        print("web_budget: no web/dist — build first (cd web && npm run build)", file=sys.stderr)
        return 2
    sizes, n = html_sizes(dist), n_interventions(ctx)
    path = REPO_ROOT / BUDGET_FILE

    if not path.exists():
        path.write_text(json.dumps(initial(sizes, n), indent=2) + "\n", encoding="utf-8")
        print(f"web_budget: created {BUDGET_FILE} from the current build ({n} interventions)")
        return 0
    budget = json.loads(path.read_text(encoding="utf-8"))

    if args.add:
        page = str(Path(args.add).resolve().relative_to(dist.resolve())) if "/" in args.add else args.add
        if page not in sizes:
            print(f"web_budget: {page} is not in the build", file=sys.stderr)
            return 2
        if not args.reason:
            print("web_budget: --add needs --reason", file=sys.stderr)
            return 2
        budget["pages"][page] = sizes[page]
        path.write_text(json.dumps(budget, indent=2) + "\n", encoding="utf-8")
        print(f"web_budget: {page} budgeted at {sizes[page] / 1e6:.2f} MB ({args.reason})")
        return 0
    if args.update:
        budget, changes = tightened(budget, sizes, n)
        path.write_text(json.dumps(budget, indent=2) + "\n", encoding="utf-8")
        print("web_budget: " + ("; ".join(changes) if changes else "nothing got lighter; budgets rebased only"))
        return 0

    over = 0
    print(f"{'page':58} {'now':>9} {'budget':>9}")
    for page, limit in budget["pages"].items():
        now, cap = sizes.get(page, 0), allowed(budget, limit, n)
        over += now > cap
        print(f"{page:58} {now / 1e6:8.2f}M {cap / 1e6:8.2f}M{'  OVER' if now > cap else ''}")
    total, cap = sum(sizes.values()), allowed(budget, budget["total_html"], n)
    over += total > cap
    print(f"{'(all HTML)':58} {total / 1e6:8.1f}M {cap / 1e6:8.1f}M{'  OVER' if total > cap else ''}")
    return 1 if over else 0


if __name__ == "__main__":
    raise SystemExit(main())
