#!/usr/bin/env python3
"""Code-health queue for CeminiDFS.

Pattern borrowed from desloppify, implementation is original and stdlib-only.

  scan    mechanical checks -> .code-health/queue.json
  review  emit blind packets, apply blind scores
  next    print the highest-scoring open item
  resolve mark an item done (guarded paths need --baseline-rerun)

The evaluation path and the export/action boundary are never scanned.
"""

from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "ceminidfs"
TESTS = ROOT / "tests"
QUEUE_DIR = ROOT / ".code-health"
QUEUE_PATH = QUEUE_DIR / "queue.json"
REVIEW_DIR = QUEUE_DIR / "review"
ALLOWLIST_PATH = QUEUE_DIR / "allowlist.txt"

# Never scanned, never queued. Evaluation path and action boundary.
EXCLUDED = (
    "src/ceminidfs/eval_loop/",
    "src/ceminidfs/pipeline/metrics.py",
    "src/ceminidfs/integrations/jev.py",
    "src/ceminidfs/jev_client.py",
    "src/ceminidfs/export/handoff.py",
    "src/ceminidfs/export/jev_gate.py",
    "src/ceminidfs/export/late_swap.py",
    "design-log/",
)

# Scanned and queued, but a fix must re-run the baseline first.
GUARDED = (
    # Projection and evaluation path. A fix here needs a baseline re-run
    # before the next comparison, so the loop leaves it alone.
    "src/ceminidfs/pipeline/backtest.py",
    "src/ceminidfs/pipeline/backtest_prepare.py",
    "src/ceminidfs/pipeline/project.py",
    "src/ceminidfs/pipeline/engine.py",
    "src/ceminidfs/pipeline/calibration.py",
    "src/ceminidfs/pipeline/regression.py",
    "src/ceminidfs/pipeline/regression_gates.py",
    "src/ceminidfs/pipeline/distributions.py",
    "src/ceminidfs/pipeline/lineup_backtest.py",
    "src/ceminidfs/pipeline/late_swap_oracle.py",
    "src/ceminidfs/pipeline/late_swap_replay.py",
    "src/ceminidfs/pipeline/permutation_test.py",
    "src/ceminidfs/pipeline/permutation_gate.py",
    "src/ceminidfs/pipeline/benchmark_replay.py",
    "src/ceminidfs/pipeline/market_benchmark.py",
    "src/ceminidfs/pipeline/sdv_benchmark.py",
    "src/ceminidfs/pipeline/luck_metrics.py",
    "src/ceminidfs/pipeline/coherence_eval.py",
    "src/ceminidfs/pipeline/premium_guard_backtest.py",
    "src/ceminidfs/models/scoring.py",
    "src/ceminidfs/models/ownership.py",
    "src/ceminidfs/models/stats.py",
    "src/ceminidfs/models/usage.py",
    "src/ceminidfs/models/ngs_elasticity.py",
    "src/ceminidfs/situational/quantiles.py",
    "src/ceminidfs/situational/eb.py",
    "src/ceminidfs/situational/engine.py",
    "src/ceminidfs/situational/features.py",
    "src/ceminidfs/situational/backtest.py",
    "src/ceminidfs/situational/fdr.py",
    "src/ceminidfs/situational/lag.py",
    "src/ceminidfs/situational/tail.py",
    "src/ceminidfs/situational/stack_corr.py",
    "src/ceminidfs/situational/injuries.py",
    "src/ceminidfs/situational/game_context.py",
)

SKIP_NAMES = {"main", "__init__", "__main__", "setUp", "tearDown"}
SKIP_DECORATORS = ("fixture", "command", "validator", "property", "cached_property")

COMPLEXITY_WARN = 10
COMPLEXITY_FAIL = 15
LONG_FUNCTION = 120
MANY_PARAMS = 9
DUP_MIN_NODES = 20


# ---------------------------------------------------------------- helpers


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def is_excluded(path: str) -> bool:
    return any(path == e or path.startswith(e) for e in EXCLUDED)


def is_guarded(path: str) -> bool:
    return any(path == g or path.startswith(g) for g in GUARDED)


def parse(path: Path) -> ast.AST | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError) as exc:
        print(f"skip {rel(path)}: {exc}", file=sys.stderr)
        return None


def source_files() -> list[Path]:
    return sorted(
        p
        for p in SRC.rglob("*.py")
        if "__pycache__" not in p.parts and not is_excluded(rel(p))
    )


def tidy_files() -> list[Path]:
    return sorted(p for p in TESTS.rglob("*.py") if "__pycache__" not in p.parts)


def docstring_ids(tree: ast.AST) -> set[int]:
    out: set[int] = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(body, list) or not body:
            continue
        first = body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
            if isinstance(first.value.value, str):
                out.add(id(first.value))
    return out


def stable_id(kind: str, path: str, symbol: str) -> str:
    raw = f"{kind}|{path}|{symbol}".encode()
    return hashlib.sha1(raw).hexdigest()[:10]


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------- defs


@dataclass
class Def:
    kind: str
    name: str
    qualname: str
    file: str
    line: int
    end_line: int
    decorators: list[str] = field(default_factory=list)
    node: ast.AST = field(default=None, repr=False)


def collect_defs(tree: ast.AST, path: str) -> list[Def]:
    out: list[Def] = []

    def visit(node: ast.AST, stack: list[str], in_class: bool, in_function: bool) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                out.append(
                    Def("class", child.name, ".".join(stack + [child.name]), path,
                        child.lineno, child.end_lineno or child.lineno,
                        _decorators(child), child)
                )
                visit(child, stack + [child.name], True, in_function)
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if in_function:
                    kind = "nested"
                elif in_class:
                    kind = "method"
                else:
                    kind = "function"
                out.append(
                    Def(kind, child.name, ".".join(stack + [child.name]), path,
                        child.lineno, child.end_lineno or child.lineno,
                        _decorators(child), child)
                )
                visit(child, stack + [child.name], in_class, True)
            else:
                visit(child, stack, in_class, in_function)

    visit(tree, [], False, False)
    return out


def _decorators(node: ast.AST) -> list[str]:
    names = []
    for dec in getattr(node, "decorator_list", []):
        try:
            names.append(ast.unparse(dec))
        except Exception:  # pragma: no cover - very old nodes
            names.append("?")
    return names


# ---------------------------------------------------------------- refs


def collect_refs(paths: list[Path]) -> tuple[Counter, Counter]:
    """Return (all names, test names)."""
    all_names: Counter = Counter()
    test_names: Counter = Counter()
    for path in paths:
        tree = parse(path)
        if tree is None:
            continue
        skip = docstring_ids(tree)
        target = test_names if path.is_relative_to(TESTS) else None
        for node in ast.walk(tree):
            name = None
            if isinstance(node, ast.Name):
                name = node.id
            elif isinstance(node, ast.Attribute):
                name = node.attr
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                if id(node) not in skip and node.value.isidentifier():
                    name = node.value
            if name:
                all_names[name] += 1
                if target is not None:
                    test_names[name] += 1
    return all_names, test_names


def imported_modules(path: Path) -> set[str]:
    tree = parse(path)
    if tree is None:
        return set()
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
            for alias in node.names:
                out.add(f"{node.module}.{alias.name}")
    return out


# ---------------------------------------------------------------- shape


def walk_shallow(node: ast.AST):
    """Walk a node without entering nested defs; they get their own finding."""
    stack = list(ast.iter_child_nodes(node))
    while stack:
        current = stack.pop()
        yield current
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        stack.extend(ast.iter_child_nodes(current))


def body_nodes(fn: ast.AST) -> list[ast.AST]:
    body = list(getattr(fn, "body", []))
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        if isinstance(body[0].value.value, str):
            body = body[1:]
    return body


def shape(fn: ast.AST) -> list[str]:
    out: list[str] = []
    for stmt in body_nodes(fn):
        for node in walk_shallow(stmt):
            if isinstance(node, (ast.expr_context, ast.operator, ast.unaryop, ast.cmpop, ast.boolop)):
                continue
            out.append(type(node).__name__)
    return out


class _Normalize(ast.NodeTransformer):
    def visit_Name(self, node):
        return ast.copy_location(ast.Name(id="_", ctx=node.ctx), node)

    def visit_FunctionDef(self, node):
        self.generic_visit(node)
        node.name = "_"
        return node

    def visit_AsyncFunctionDef(self, node):
        self.generic_visit(node)
        node.name = "_"
        return node

    def visit_ClassDef(self, node):
        self.generic_visit(node)
        node.name = "_"
        return node

    def visit_Attribute(self, node):
        self.generic_visit(node)
        node.attr = "_"
        return node

    def visit_arg(self, node):
        self.generic_visit(node)
        node.arg = "_"
        return node

    def visit_Constant(self, node):
        return ast.copy_location(ast.Constant(value=type(node.value).__name__), node)


def normalized_dump(fn: ast.AST) -> str:
    clone = _Normalize().visit(copy.deepcopy(fn))
    ast.fix_missing_locations(clone)
    return ast.dump(clone, annotate_fields=False, include_attributes=False)


def complexity(fn: ast.AST) -> int:
    score = 1
    for node in walk_shallow(fn):
        if isinstance(node, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler,
                             ast.With, ast.AsyncWith, ast.IfExp, ast.Assert,
                             ast.match_case)):
            score += 1
        elif isinstance(node, ast.comprehension):
            score += 1 + len(node.ifs)
        elif isinstance(node, ast.BoolOp):
            score += len(node.values) - 1
    return score


# ---------------------------------------------------------------- checks


def subclasses(tree: ast.AST) -> set[str]:
    """Qualnames of classes that inherit from something, i.e. framework hooks."""
    out: set[str] = set()

    def visit(node: ast.AST, stack: list[str]) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                qual = ".".join(stack + [child.name])
                if child.bases:
                    out.add(qual)
                visit(child, stack + [child.name])
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                visit(child, stack + [child.name])
            else:
                visit(child, stack)

    visit(tree, [])
    return out


def check_dead_code(defs: list[Def], refs: Counter, hooks: set[str]) -> list[dict]:
    out = []
    for d in defs:
        if d.name in SKIP_NAMES or d.name.startswith("__"):
            continue
        if any(s in dec for dec in d.decorators for s in SKIP_DECORATORS):
            continue
        if refs.get(d.name, 0) > 0:
            continue
        private = d.name.startswith("_")
        owner = d.qualname.rsplit(".", 1)[0] if "." in d.qualname else ""
        framework_hook = d.kind == "method" and owner in hooks
        if framework_hook:
            detail = f"unreferenced method '{d.name}' on subclass {owner} (framework hook?)"
            mech = 20.0
        elif private:
            detail = f"unreferenced {d.kind} '{d.name}' (private)"
            mech = 70.0
        else:
            detail = f"unreferenced {d.kind} '{d.name}' (public: check dynamic dispatch)"
            mech = 45.0
        out.append({
            "kind": "dead_code",
            "file": d.file,
            "line": d.line,
            "symbol": d.qualname,
            "detail": detail,
            "mechanical": mech,
        })
    return out


def check_unused_imports(tree: ast.AST, path: str) -> list[dict]:
    lines = (ROOT / path).read_text(encoding="utf-8").splitlines()
    used = Counter()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            used[node.id] += 1
        elif isinstance(node, ast.Attribute):
            used[node.attr] += 1
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value.isidentifier():
                used[node.value] += 1

    out = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        if isinstance(node, ast.ImportFrom) and node.module == "__future__":
            continue
        if "noqa" in lines[node.lineno - 1].lower():
            continue
        for alias in node.names:
            if alias.name == "*":
                continue
            bound = alias.asname or alias.name.split(".")[0]
            if used.get(bound, 0) == 0:
                out.append({
                    "kind": "unused_import",
                    "file": path,
                    "line": node.lineno,
                    "symbol": bound,
                    "detail": f"import '{alias.name}' is never used in this module",
                    "mechanical": 30.0,
                })
    return out


def check_duplication(defs: list[Def]) -> list[dict]:
    groups: dict[tuple[str, ...], list[Def]] = defaultdict(list)
    sizes: dict[tuple[str, ...], int] = {}
    for d in defs:
        if d.kind == "class":
            continue
        shp = shape(d.node)
        if len(shp) < DUP_MIN_NODES:
            continue
        key = tuple(shp)
        groups[key].append(d)
        sizes[key] = len(shp)

    out = []
    seen: set[tuple[str, str, str]] = set()
    for key, members in groups.items():
        if len(members) < 2:
            continue
        members = sorted(members, key=lambda d: (d.file, d.line))
        for i in range(len(members) - 1):
            for j in range(i + 1, len(members)):
                a, b = members[i], members[j]
                if a.qualname == b.qualname and a.file == b.file:
                    continue
                same_logic = normalized_dump(a.node) == normalized_dump(b.node)
                ratio = SequenceMatcher(None, key, key).ratio()
                if not same_logic:
                    ratio = 0.75
                tag = (a.qualname, b.file, b.qualname)
                if tag in seen:
                    continue
                seen.add(tag)
                out.append({
                    "kind": "duplication",
                    "file": b.file,
                    "line": b.line,
                    "symbol": b.qualname,
                    "detail": f"same code shape as {a.file}:{a.line} ({a.qualname});"
                              f" {sizes[key]} nodes,"
                              f" {'identical logic' if same_logic else 'renamed copy'}",
                    "mechanical": round(40.0 + 45.0 * ratio, 1),
                })
    return out


def check_complexity(defs: list[Def]) -> list[dict]:
    out = []
    for d in defs:
        if d.kind == "class":
            continue
        cx = complexity(d.node)
        lines = d.end_line - d.line + 1
        arg_spec = d.node.args
        params = len(arg_spec.posonlyargs) + len(arg_spec.args)

        if cx >= COMPLEXITY_FAIL:
            out.append({
                "kind": "complexity",
                "file": d.file,
                "line": d.line,
                "symbol": d.qualname,
                "detail": f"cyclomatic complexity {cx} (fail >= {COMPLEXITY_FAIL})",
                "mechanical": min(100.0, 45.0 + (cx - COMPLEXITY_FAIL) * 4.0),
            })
        elif cx >= COMPLEXITY_WARN:
            out.append({
                "kind": "complexity",
                "file": d.file,
                "line": d.line,
                "symbol": d.qualname,
                "detail": f"cyclomatic complexity {cx} (warn >= {COMPLEXITY_WARN})",
                "mechanical": 30.0 + (cx - COMPLEXITY_WARN) * 3.0,
            })

        if lines > LONG_FUNCTION:
            out.append({
                "kind": "long_function",
                "file": d.file,
                "line": d.line,
                "symbol": d.qualname,
                "detail": f"{lines} lines (limit {LONG_FUNCTION})",
                "mechanical": min(90.0, 30.0 + (lines - LONG_FUNCTION) * 0.3),
            })

        if params > MANY_PARAMS:
            out.append({
                "kind": "many_params",
                "file": d.file,
                "line": d.line,
                "symbol": d.qualname,
                "detail": f"{params} positional parameters (limit {MANY_PARAMS})",
                "mechanical": 35.0,
            })
    return out


def check_test_gaps(defs: list[Def], test_names: Counter, tested_modules: set[str]) -> list[dict]:
    out = []
    module_seen: set[str] = set()
    for d in defs:
        module = module_of(d.file)
        if d.kind in ("class", "nested") or d.name.startswith("_"):
            continue
        if module not in tested_modules:
            if module not in module_seen:
                module_seen.add(module)
                out.append({
                    "kind": "test_gap",
                    "file": d.file,
                    "line": 1,
                    "symbol": module,
                    "detail": f"no test imports {module}",
                    "mechanical": 45.0,
                })
            continue
        if test_names.get(d.name, 0) == 0:
            # Only a large or branchy function is a real gap; a small helper
            # called through its public caller is not.
            cx = complexity(d.node)
            lines = d.end_line - d.line + 1
            if cx < COMPLEXITY_WARN and lines < 60:
                continue
            out.append({
                "kind": "test_gap",
                "file": d.file,
                "line": d.line,
                "symbol": d.qualname,
                "detail": f"public {d.kind} '{d.name}' never named in tests"
                          f" (complexity {cx}, {lines} lines)",
                "mechanical": 35.0,
            })
    return out


def module_of(path: str) -> str:
    p = Path(path).with_suffix("")
    parts = p.parts
    if parts and parts[0] == "src":
        parts = parts[1:]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def tested_module_set() -> set[str]:
    out: set[str] = set()
    for path in tidy_files():
        out |= imported_modules(path)
    return out


# ---------------------------------------------------------------- queue


def load_allowlist() -> set[str]:
    if not ALLOWLIST_PATH.exists():
        return set()
    ids = set()
    for line in ALLOWLIST_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            ids.add(line)
    return ids


def load_queue() -> dict:
    if QUEUE_PATH.exists():
        return json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
    return {"version": 1, "generated": None, "files_scanned": 0, "findings": []}


def rank(item: dict) -> tuple:
    """Reviewed items come first; an unreviewed mechanical score is a guess."""
    return (
        item["status"] != "open",
        item.get("review") is None,
        -item["composite"],
        item["file"],
        item["line"],
    )


def save_queue(state: dict) -> None:
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    state["findings"].sort(key=rank)
    QUEUE_PATH.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def composite(mech: float, review: float | None) -> float:
    if review is None:
        return round(mech, 1)
    return round(0.25 * mech + 0.75 * review, 1)


def merge(state: dict, fresh: list[dict]) -> dict:
    allow = load_allowlist()
    old = {f["id"]: f for f in state["findings"]}
    merged = []
    for item in fresh:
        fid = stable_id(item["kind"], item["file"], item["symbol"])
        if fid in allow:
            continue
        prior = old.get(fid, {})
        review = prior.get("review")
        entry = {
            "id": fid,
            "kind": item["kind"],
            "file": item["file"],
            "line": item["line"],
            "symbol": item["symbol"],
            "detail": item["detail"],
            "guarded": is_guarded(item["file"]),
            "mechanical": item["mechanical"],
            "review": review,
            "review_notes": prior.get("review_notes"),
            "composite": composite(item["mechanical"], review),
            "status": prior.get("status", "open"),
            "note": prior.get("note"),
            "first_seen": prior.get("first_seen", now()),
            "updated": now(),
        }
        merged.append(entry)
    state["findings"] = merged
    state["generated"] = now()
    return state


def find(state: dict, fid: str) -> dict | None:
    for item in state["findings"]:
        if item["id"] == fid:
            return item
    return None


# ---------------------------------------------------------------- commands


def cmd_scan(args) -> int:
    files = source_files()
    defs: list[Def] = []
    per_file_tree: dict[str, ast.AST] = {}
    hooks: set[str] = set()
    for path in files:
        tree = parse(path)
        if tree is None:
            continue
        per_file_tree[rel(path)] = tree
        defs.extend(collect_defs(tree, rel(path)))
        hooks |= subclasses(tree)

    ref_paths = files + tidy_files()
    refs, test_names = collect_refs(ref_paths)

    findings: list[dict] = []
    findings += check_dead_code(defs, refs, hooks)
    for path, tree in per_file_tree.items():
        findings += check_unused_imports(tree, path)
    findings += check_duplication(defs)
    findings += check_complexity(defs)
    findings += check_test_gaps(defs, test_names, tested_module_set())

    state = load_queue()
    state = merge(state, findings)
    state["files_scanned"] = len(files)
    save_queue(state)

    guarded = sum(1 for f in state["findings"] if f["guarded"])
    print(f"scanned {len(files)} files, {len(state['findings'])} findings"
          f" ({guarded} guarded on the scoring path)")
    by_kind = Counter(f["kind"] for f in state["findings"])
    for kind, n in by_kind.most_common():
        print(f"  {kind:<16} {n}")
    return 0


def cmd_status(args) -> int:
    state = load_queue()
    findings = state["findings"]
    print(f"queue: {QUEUE_PATH.relative_to(ROOT)}  (seen {state['generated']})")
    print(f"files scanned: {state['files_scanned']}   findings: {len(findings)}")
    by_status = Counter(f["status"] for f in findings)
    print("status:", ", ".join(f"{k} {v}" for k, v in sorted(by_status.items())) or "empty")
    print("kinds: ", ", ".join(f"{k} {v}" for k, v in Counter(f["kind"] for f in findings).most_common()))
    print("\ntop open  (* = mechanical score, not yet blind-reviewed):")
    for item in [f for f in findings if f["status"] == "open"][:8]:
        flag = " [guarded]" if item["guarded"] else ""
        mark = "*" if item["review"] is None else " "
        print(f"  {item['id']}  {item['composite']:>5.1f}{mark} {item['kind']:<14}"
              f" {item['file']}:{item['line']}{flag}")
    return 0


def cmd_next(args) -> int:
    state = load_queue()
    pool = [f for f in state["findings"] if f["status"] == "open"]
    if not args.include_guarded:
        pool = [f for f in pool if not f["guarded"]]
    if not pool:
        print("queue empty" if not args.include_guarded else "nothing open")
        return 0
    item = min(pool, key=rank)
    if args.json:
        print(json.dumps(item, indent=2))
        return 0
    print(f"{item['id']}  score {item['composite']}  {item['kind']}")
    print(f"  {item['file']}:{item['line']}  {item['symbol']}")
    print(f"  {item['detail']}")
    if item["guarded"]:
        print("  GUARDED: fix needs a baseline re-run before the next comparison")
    if item["review"] is not None:
        print(f"  blind review {item['review']}  {item.get('review_notes') or ''}")
    else:
        print("  mechanical score only; run `review emit` to blind-score it")
    return 0


def cmd_review(args) -> int:
    state = load_queue()
    if args.action == "emit":
        return review_emit(state, args)
    if args.action == "apply":
        return review_apply(state, args)
    print("review needs emit or apply", file=sys.stderr)
    return 2


def review_emit(state: dict, args) -> int:
    pool = [f for f in state["findings"] if f["status"] == "open" and f["review"] is None]
    if not args.include_guarded:
        pool = [f for f in pool if not f["guarded"]]
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    pending = REVIEW_DIR / "pending"
    pending.mkdir(exist_ok=True)

    rubric = {
        "naming": "Do names state the thing plainly? 1-5.",
        "abstraction": "Does the abstraction match the job, with no extra layer? 1-5.",
        "boundary": "Does the module own one job, with a clear edge? 1-5.",
        "cohesion": "Do the parts belong together? 1-5.",
        "score": "sum(1..4) / 20 * 100, integer 0-100",
    }
    scores = {}
    emitted = 0
    for item in pool[: args.limit]:
        if item["kind"] == "test_gap" and item["line"] == 1:
            code = module_inventory(item["file"])
        else:
            code = snippet(item["file"], item["line"])
        if not code:
            continue
        packet = {
            "id": item["id"],
            "kind": item["kind"],
            "artifact": {
                "file": item["file"],
                "symbol": item["symbol"],
                "code": code,
            },
            "rubric": rubric,
        }
        text = json.dumps(packet, indent=2)
        if any(k in text for k in ('"author"', '"commit"')):
            raise SystemExit("blindness check failed: packet leaks author or commit")
        (pending / f"{item['id']}.json").write_text(text + "\n", encoding="utf-8")
        scores[item["id"]] = {"score": 0, "notes": ""}
        emitted += 1

    template = REVIEW_DIR / "scores.template.json"
    template.write_text(json.dumps(scores, indent=2) + "\n", encoding="utf-8")
    print(f"emitted {emitted} blind packets -> {pending.relative_to(ROOT)}")
    print(f"fill {template.relative_to(ROOT)}, then: review apply <file>")
    return 0


def review_apply(state: dict, args) -> int:
    path = Path(args.file)
    if not path.is_absolute():
        path = ROOT / path
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        payload = {row["id"]: row for row in payload}
    applied = 0
    for fid, row in payload.items():
        item = find(state, fid)
        if item is None:
            print(f"unknown id {fid}", file=sys.stderr)
            continue
        score = float(row.get("score", 0))
        if not 0 <= score <= 100:
            print(f"bad score {score} for {fid}", file=sys.stderr)
            continue
        item["review"] = score
        item["review_notes"] = (row.get("notes") or "").strip() or None
        item["composite"] = composite(item["mechanical"], score)
        item["updated"] = now()
        applied += 1
    save_queue(state)
    print(f"applied {applied} review scores")
    return 0


def module_inventory(path: str) -> str:
    """Public surface of a module, for a module-level review packet."""
    full = ROOT / path
    tree = parse(full) if full.exists() else None
    if tree is None:
        return ""
    doc = ast.get_docstring(tree) or ""
    rows = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name.startswith("_"):
                continue
            rows.append(f"  {node.name:<32} line {node.lineno}")
    return (
        f"# {path}\n{doc[:400]}\n\npublic surface:\n" + "\n".join(rows[:60])
    ).strip()


def snippet(path: str, line: int, context: int = 6, cap: int = 220) -> str:
    full = ROOT / path
    if not full.exists():
        return ""
    lines = full.read_text(encoding="utf-8").splitlines()
    tree = parse(full)
    end = line
    if tree is not None:
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if node.lineno == line:
                    end = node.end_lineno or line
                    break
    start = max(1, line - context)
    end = min(len(lines), max(end, line) + context, start + cap)
    return "\n".join(lines[start - 1 : end])


def cmd_resolve(args) -> int:
    state = load_queue()
    item = find(state, args.id)
    if item is None:
        print(f"unknown id {args.id}", file=sys.stderr)
        return 2
    if item["guarded"] and not args.baseline_rerun:
        print("refused: guarded scoring-path item.", file=sys.stderr)
        print("re-run the baseline, then pass --baseline-rerun.", file=sys.stderr)
        return 3
    item["status"] = "resolved"
    item["note"] = args.note or item.get("note")
    item["updated"] = now()
    save_queue(state)
    print(f"{args.id} resolved")
    return 0


def cmd_defer(args) -> int:
    state = load_queue()
    item = find(state, args.id)
    if item is None:
        print(f"unknown id {args.id}", file=sys.stderr)
        return 2
    item["status"] = "deferred"
    item["note"] = args.reason
    item["updated"] = now()
    save_queue(state)
    print(f"{args.id} deferred: {args.reason}")
    return 0


def cmd_reopen(args) -> int:
    state = load_queue()
    item = find(state, args.id)
    if item is None:
        print(f"unknown id {args.id}", file=sys.stderr)
        return 2
    item["status"] = "open"
    item["updated"] = now()
    save_queue(state)
    print(f"{args.id} reopened")
    return 0


# ---------------------------------------------------------------- main


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Code-health queue (stdlib only)")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("scan", help="run mechanical checks and merge into the queue")
    s.set_defaults(func=cmd_scan)

    s = sub.add_parser("status", help="queue summary")
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("next", help="print the highest-scoring open item")
    s.add_argument("--include-guarded", action="store_true")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_next)

    s = sub.add_parser("review", help="blind review pass")
    s.add_argument("action", choices=["emit", "apply"])
    s.add_argument("file", nargs="?", help="scores file for apply")
    s.add_argument("--limit", type=int, default=12)
    s.add_argument("--include-guarded", action="store_true")
    s.set_defaults(func=cmd_review)

    s = sub.add_parser("resolve", help="mark an item done")
    s.add_argument("id")
    s.add_argument("--note")
    s.add_argument("--baseline-rerun", action="store_true")
    s.set_defaults(func=cmd_resolve)

    s = sub.add_parser("defer", help="park an item")
    s.add_argument("id")
    s.add_argument("--reason", required=True)
    s.set_defaults(func=cmd_defer)

    s = sub.add_parser("reopen", help="put an item back in the queue")
    s.add_argument("id")
    s.set_defaults(func=cmd_reopen)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "review" and args.action == "apply" and not args.file:
        print("review apply needs a scores file", file=sys.stderr)
        return 2
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
