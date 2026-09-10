"""Versioned contracts, conservative snapshots and fail-closed completion.

This is a cooperating local runner, not a sandbox or an identity provider.
"""
import argparse
import contextlib
import difflib
import fnmatch
import hashlib
import importlib.resources
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid
import xml.etree.ElementTree as ET

from . import __version__

SCHEMA = 1
RULE_VERSION = "2026-09-10-r5"
ROLES = {"entry", "state", "map", "history", "maintenance"}
EXCLUDED = {".git", ".artifacts", "__pycache__", ".venv", "node_modules"}
SECRET = {".env", "credentials.json", "secrets.json"}


class Invalid(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise Invalid(message)


def digest(data):
    if not isinstance(data, bytes):
        data = json.dumps(data, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def atomic(path, value):
    atomic_bytes(path, (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def atomic_bytes(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def inside(root, rel):
    require(isinstance(rel, str) and rel and not Path(rel).is_absolute(), "Expected relative project path")
    root = Path(root).resolve()
    path = root / rel
    require(path.resolve().is_relative_to(root), "Path escapes project")
    for part in [path, *path.parents]:
        if part == root:
            break
        require(not part.is_symlink() and not (hasattr(part, "is_junction") and part.is_junction()), "Linked paths unsupported")
    return path


def secret(path):
    n = Path(path).name.lower()
    return n in SECRET or (n.startswith(".env.") and n != ".env.example") or n.endswith((".pem", ".key", ".pfx"))


def snapshot(root):
    root = Path(root).resolve()
    result = {}
    for base, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDED)
        for d in dirs:
            inside(root, (Path(base) / d).relative_to(root).as_posix())
        for name in sorted(files):
            rel = (Path(base) / name).relative_to(root).as_posix()
            if secret(rel) or name.endswith(".pyc"):
                continue
            p = inside(root, rel)
            result[rel] = digest(p.read_bytes())
    return result


def changed(before, after):
    return sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))


@contextlib.contextmanager
def lock(root):
    path = inside(root, ".artifacts/jxcheck.lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise Invalid("Runner busy or interrupted; inspect lock, confirm process stopped, then recover")
    try:
        os.write(fd, json.dumps({"pid": os.getpid(), "time": time.time()}).encode())
        os.close(fd)
        yield
    finally:
        path.unlink(missing_ok=True)


def identity():
    return digest({p.name: digest(p.read_bytes()) for p in importlib.resources.files("jxcheck").iterdir() if p.name.endswith(".py")})


def load_project(root):
    require(not (root / '.artifacts/install.pending.json').exists(), 'Interrupted installation; inspect recovery journal')
    c = read(root / ".project" / "project.json")
    installed = read(root / '.project/framework.lock.json')
    require(installed.get('runner_hash') == identity() and installed.get('runner') == __version__ and installed.get('rule_version') == RULE_VERSION and installed.get('source_hash'), 'Installed framework/runner lock mismatch')
    require(c.get("schema") == SCHEMA and c.get("runner") == __version__, "Unsupported schema/runner")
    require(c.get("rule_version") == RULE_VERSION, "Framework version mismatch; upgrade required")
    require(isinstance(c.get("requirements"), list) and c["requirements"], "Missing requirements")
    require(len(c["requirements"]) == len(set(c["requirements"])), "Duplicate requirements")
    require(c.get("environment_id") and c.get("build_id"), "Missing non-secret environment/build identifiers")
    bindings = c.get("bindings", {})
    require(ROLES <= bindings.keys(), "Missing mandatory binding")
    for role, b in bindings.items():
        require(all(b.get(k) for k in ("path", "owner", "read_when", "update_when", "verify")), "Incomplete binding: " + role)
        p = inside(root, b["path"])
        require(p.is_file(), "Missing bound file: " + role)
        require(not secret(p), "Secret cannot be a binding")
    checks = c.get("checks", [])
    require(isinstance(checks, list) and checks, "No checks configured")
    ids = set()
    reports = set()
    covered = set()
    for ch in checks:
        require(all(ch.get(k) for k in ("id", "requirements", "expected", "owner", "kind", "steps", "evidence")), "Incomplete check")
        require(re.fullmatch(r"[A-Za-z0-9_-]+", ch["id"]), "Invalid check ID")
        require(ch["id"] not in ids, "Duplicate check ID")
        ids.add(ch["id"])
        require(type(ch.get("required")) is bool, "Required must be boolean")
        require(set(ch["requirements"]) <= set(c["requirements"]), "Unknown requirement")
        if ch["required"]:
            covered.update(ch["requirements"])
        require(ch["kind"] in {"junit", "json", "document", "manual"}, "Unsupported evidence adapter")
        if ch["kind"] in {"junit", "json"}:
            require(isinstance(ch.get("argv"), list) and ch["argv"] and all(isinstance(v, str) for v in ch["argv"]), "argv must be string array")
            require(inside(root, ch.get("cwd", "")).is_dir(), "Missing cwd")
            require(ch.get("report", "").startswith("{run}/"), "Report must be fresh run output")
            require(ch['report'] not in reports, 'Each check requires a unique report')
            reports.add(ch['report'])
            require(type(ch.get('timeout', 60)) in {int, float} and 0 < ch.get('timeout', 60) <= 3600, 'Invalid timeout')
            require(all(isinstance(a, str) and a.startswith('{run}/') for a in ch.get('attachments', [])), 'Attachments must be fresh run outputs')
            if ch["kind"] == "json":
                require(isinstance(ch.get("assertions"), dict) and ch["assertions"], "JSON needs explicit assertions")
            if ch["kind"] == "junit":
                require(isinstance(ch.get("expected_cases"), list) and ch["expected_cases"], "JUnit requires protected case names")
            exe = ch["argv"][0]
            require(exe == "{python}" or shutil.which(exe) is not None or Path(exe).is_file(), "Executable unavailable: " + exe)
        if ch["kind"] == "document":
            require(ch.get("documents") or ch.get("equal"), "No document assertions")
            for p in ch.get("documents", []):
                inside(root, p)
    require(covered >= set(c["requirements"]), "Requirements lack required checks")
    return c


def doctor(root):
    root = Path(root).resolve()
    try:
        c = load_project(root)
        return {"status": "ok", "runner": __version__, "checks": len(c["checks"]),
                "coverage": "configured requirements only; semantic suitability requires review",
                "entry": "CLI only; no host hook/remote protection installed"}
    except (Invalid, OSError, ValueError, TypeError, KeyError) as e:
        return {"status": "blocked", "reason": str(e)}


def task_path(root, task):
    require(re.fullmatch(r"[A-Za-z0-9_-]+", task or ""), "Invalid task ID")
    return root / ".project" / "tasks" / (task + ".json")


def capture_task(root, task, spec, scope, apply=False):
    root = Path(root).resolve()
    c = load_project(root)
    sp = inside(root, spec)
    require(sp.is_file() and not secret(sp), "Missing non-secret Task Spec")
    txt = sp.read_text(encoding="utf-8-sig")
    require(all("## " + h in txt for h in ["目标", "上下文", "范围", "约束", "验收"]), "Spec needs five sections")
    require(scope and all(isinstance(s, str) and s and not Path(s).is_absolute() and ".." not in Path(s).parts for s in scope), "Invalid write scope")
    p = task_path(root, task)
    require(not p.exists(), "Task already frozen; use new revision ID, do not overwrite")
    data = {"schema": SCHEMA, "id": task, "spec": spec, "spec_hash": digest(sp.read_bytes()),
            "project_hash": digest(c), "scope": scope, "baseline": snapshot(root),
            "captured_at": time.time(), "authorization": "external conversation required; this is not human authentication"}
    if apply:
        with lock(root):
            require(not p.exists(), "Concurrent task capture")
            atomic(p, data)
    return {"status": "captured" if apply else "preview", "task": task, "scope": scope, "project_hash": digest(c)}


def contract(root, task):
    root = Path(root).resolve()
    c = load_project(root)
    p = task_path(root, task)
    t = read(p)
    require(t["id"] == task and t["schema"] == SCHEMA, "Wrong task record")
    require(t["project_hash"] == digest(c), "Check contract changed; review diff and capture new task revision")
    require(t["spec_hash"] == digest(inside(root, t["spec"]).read_bytes()), "Spec changed; capture new task revision")
    now = snapshot(root)
    own = p.relative_to(root).as_posix()
    delta = [f for f in changed(t["baseline"], now) if f != own and not any(fnmatch.fnmatchcase(f, s) for s in t["scope"])]
    require(not delta, "Out of scope changes: " + ", ".join(delta))
    return c, t, now


def document_check(root, ch):
    failures = []
    for rel in ch.get("documents", []):
        p = inside(root, rel)
        text = p.read_text(encoding="utf-8-sig")
        for target in re.findall(r"(?<!!)\[[^\]]*\]\(([^)]+)\)", text):
            target = target.split("#")[0].strip("<>")
            if target and not re.match(r"[a-zA-Z]+:", target):
                dest = p.parent / target
                require(dest.resolve().is_relative_to(root), "Document link escapes project")
                if not dest.exists():
                    failures.append("Broken link in " + rel + ": " + target)
    for pair in ch.get("equal", []):
        require(len(pair) == 2, "Equal assertion requires two file/key references")
        vals = []
        for ref in pair:
            f, k = ref.split("#", 1)
            vals.append(read(inside(root, f))[k])
        if vals[0] != vals[1]:
            failures.append("State mismatch: " + str(pair))
    return {"status": "fail" if failures else "pass", "failures": failures,
            "limitation": "Local file links and declared JSON equality only; semantic interpretation not inferred"}


def execute(root, run, ch):
    if ch["kind"] == "manual":
        return {"status": "not_run", "reason": "Human review pending; CLI cannot authenticate the reviewer"}
    if ch["kind"] == "document":
        return document_check(root, ch)
    def expand(v):
        return v.replace("{python}", sys.executable).replace("{run}", str(run)).replace("{root}", str(root))
    report = Path(expand(ch["report"]))
    require(report.resolve().is_relative_to(run), "Report escaped run")
    require(not report.exists(), 'Report already exists before check; refusing reused evidence')
    argv = [expand(v) for v in ch["argv"]]
    proc = subprocess.run(argv, cwd=inside(root, ch["cwd"]), capture_output=True, timeout=ch.get("timeout", 60), env={**os.environ, "PYTHONPYCACHEPREFIX": str(run / "pycache"), "PYTHONDONTWRITEBYTECODE": "1"})
    # Do not persist arbitrary stdout/stderr: programs may print credentials.
    result = {"exit_code": proc.returncode, "stdout_bytes": len(proc.stdout), "stderr_bytes": len(proc.stderr)}
    if proc.returncode != 0:
        return {**result, "status": "fail", "reason": "Command failed; inspect locally without copying secrets"}
    require(report.is_file(), "Structured report missing")
    if ch["kind"] == "junit":
        xml = ET.parse(report).getroot()
        cases = list(xml.iter("testcase"))
        failures = sum(1 for tc in cases if tc.find("failure") is not None or tc.find("error") is not None)
        skips = sum(1 for tc in cases if tc.find("skipped") is not None)
        suites = list(xml.iter('testsuite')) + ([xml] if xml.tag == 'testsuites' else [])
        require(not any(int(s.get('failures', '0')) > 0 or int(s.get('errors', '0')) > 0 for s in suites), 'JUnit suite reports errors/failures')
        if any(int(s.get('skipped', '0')) > 0 for s in suites):
            skips = max(skips, 1)
        require(cases, "Zero tests")
        require(set(ch["expected_cases"]) <= {tc.get("name") for tc in cases}, "Protected regression case removed/renamed")
        require(not list(xml.iter("error")) and not list(xml.iter("failure")), "JUnit reports errors/failures")
        result.update(tests=len(cases), failures=failures, skipped=skips, status="skip" if skips else "pass")
    else:
        data = read(report)
        require(all(k in data and type(data[k]) is type(v) and data[k] == v for k, v in ch["assertions"].items()), "Declared assertion failed")
        result["status"] = "pass"
    for name in ch.get("attachments", []):
        p = Path(expand(name))
        require(p.resolve().is_relative_to(run) and p.is_file() and p.stat().st_size > 0, "Required attachment missing")
    return result


def verify(root, task):
    root = Path(root).resolve()
    with lock(root):
        c, t, before = contract(root, task)
        run_id = task + "-" + uuid.uuid4().hex
        run = root / ".artifacts" / "runs" / run_id
        run.mkdir(parents=True)
        atomic(root / ".artifacts" / (task + ".latest.json"), {"run": run_id, "state": "running"})
        results = []
        start = time.time()
        for ch in c["checks"]:
            try:
                result = execute(root, run, ch)
            except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired, ET.ParseError) as e:
                result = {"status": "error", "reason": str(e)}
            results.append({"id": ch["id"], "required": ch["required"], **result})
        after = snapshot(root)
        files = {}
        for p in run.rglob("*"):
            if p.is_file() and "pycache" not in p.relative_to(run).parts:
                require(not secret(p), "Secret-named run output rejected")
                require(p.resolve().is_relative_to(run) and not p.is_symlink(), "Invalid output path")
                files[p.relative_to(run).as_posix()] = digest(p.read_bytes())
        receipt = {"schema": SCHEMA, "runner": __version__, "runner_hash": identity(), "task": task,
                   "contract_hash": digest(t), "project_hash": digest(c), "snapshot": before,
                   "changed_during_run": changed(before, after), "results": results, "files": files,
                   "started_at": start, "duration_seconds": time.time() - start,
                   "runtime": sys.version, "environment_id": c["environment_id"], "build_id": c["build_id"],
                   "limitations": "Local cooperating runner. No human identity, secret environment attestation, or host interception."}
        atomic(run / "receipt.json", receipt)
        atomic(root / ".artifacts" / (task + ".latest.json"), {"run": run_id, "state": "complete", "receipt_hash": digest(receipt)})
    return finish(root, task)


def finish(root, task):
    root = Path(root).resolve()
    try:
        c, t, now = contract(root, task)
        require(not (root / ".artifacts" / "jxcheck.lock").exists(), "Verification in progress or interrupted")
        pointer = read(root / ".artifacts" / (task + ".latest.json"))
        require(pointer.get("state") == "complete", "Incomplete run")
        require(re.fullmatch(re.escape(task) + r"-[a-f0-9]{32}", pointer["run"]), "Invalid run reference")
        run = root / ".artifacts" / "runs" / pointer["run"]
        r = read(run / "receipt.json")
        require(digest(r) == pointer["receipt_hash"], "Receipt changed")
        require(r["task"] == task and r["contract_hash"] == digest(t) and r["project_hash"] == digest(c), "Evidence contract mismatch")
        if r["snapshot"] != now or r["changed_during_run"] or r["runner_hash"] != identity():
            return {"status": "stale", "reason": "Inputs or runner changed", "changes": changed(r["snapshot"], now)}
        for rel, sha in r["files"].items():
            p = inside(run, rel)
            require(p.is_file() and digest(p.read_bytes()) == sha, "Evidence attachment missing/changed: " + rel)
        require([x["id"] for x in r["results"]] == [x["id"] for x in c["checks"]], "Missing check results")
        blocked, manual = [], []
        for ch, result in zip(c["checks"], r["results"]):
            if ch["required"] and result["status"] != "pass":
                (manual if ch["kind"] == "manual" else blocked).append(ch["id"])
        return {"status": "blocked" if blocked else "pending_manual" if manual else "ready",
                "blocked": blocked, "pending_manual": manual, "results": r["results"],
                "evidence": str(run / "receipt.json"), "meaning": "Meets configured checks only; not universal business correctness"}
    except (Invalid, OSError, ValueError, KeyError, TypeError) as e:
        return {"status": "blocked", "reason": str(e)}


def installation(root, manifest, apply=False, upgrade=False):
    """Reviewable owned-file updates; user-edited files are conflicts."""
    root = Path(root).resolve()
    source = Path(manifest).resolve()
    plan = read(source)
    require(plan.get("schema") == SCHEMA and isinstance(plan.get("files"), dict) and plan["files"], "Invalid installation manifest")
    lockfile = root / ".project" / "framework.lock.json"
    old = read(lockfile) if lockfile.exists() else {"files": {}}
    changes, conflicts, contents = [], [], {}
    for rel, content in plan["files"].items():
        require(isinstance(content, str), "Manifest file content must be text")
        require(not rel.startswith((".artifacts/", ".git/")) and rel != ".project/framework.lock.json" and not secret(rel), "Reserved installation target")
        p = inside(root, rel)
        data = content.encode("utf-8")
        current = p.read_bytes() if p.exists() else None
        if current == data:
            continue
        if current is not None and (not upgrade or old["files"].get(rel) != digest(current)):
            conflicts.append(rel)
        changes.append({"path": rel, "action": "update" if current is not None else "create",
                        "before": digest(current) if current is not None else None,
                        "diff": "".join(difflib.unified_diff((current or b"").decode("utf-8-sig").splitlines(True), content.splitlines(True), fromfile=rel, tofile=rel))})
        contents[rel] = data
    result = {"status": "conflict" if conflicts else "preview", "changes": changes, "conflicts": conflicts,
              "note": "No automatic deletion; existing project records must be mapped in the manifest"}
    if not apply or conflicts:
        return result
    with lock(root):
        for change in changes:
            p = inside(root, change["path"])
            require((digest(p.read_bytes()) if p.exists() else None) == change["before"], "Concurrent change; preview again")
        bid = uuid.uuid4().hex
        backup = root / ".artifacts" / "upgrades" / bid
        before = {rel: (inside(root, rel).read_bytes().hex() if inside(root, rel).exists() else None) for rel in contents}
        before[".project/framework.lock.json"] = lockfile.read_bytes().hex() if lockfile.exists() else None
        newlock = {"schema": SCHEMA, "runner": __version__, "rule_version": RULE_VERSION, "runner_hash": identity(),
                   "source_hash": digest(plan), "files": {**old["files"], **{rel: digest(v.encode()) for rel, v in plan["files"].items()}}}
        intended = {rel: digest(v) for rel, v in contents.items()}
        intended[".project/framework.lock.json"] = digest((json.dumps(newlock, ensure_ascii=False, indent=2) + "\n").encode())
        atomic(backup / "recovery.json", {"before": before, "after": intended})
        atomic(root / '.artifacts/install.pending.json', {'backup': bid})
        for rel, data in contents.items():
            p = inside(root, rel)
            p.parent.mkdir(parents=True, exist_ok=True)
            atomic_bytes(p, data)
        atomic(lockfile, newlock)
        (root / '.artifacts/install.pending.json').unlink()
        result.update(status="applied", backup=bid)
    return result


def restore(root, bid, apply=False):
    root = Path(root).resolve()
    require(re.fullmatch(r"[a-f0-9]{32}", bid or ""), "Invalid backup ID")
    recovery = read(root / ".artifacts" / "upgrades" / bid / "recovery.json")
    conflicts = []
    for rel, sha in recovery["after"].items():
        p = inside(root, rel)
        current = digest(p.read_bytes()) if p.exists() else None
        before = recovery["before"][rel]
        if current not in {sha, digest(bytes.fromhex(before)) if before is not None else None}:
            conflicts.append(rel)
    require(not conflicts, "Restore conflicts; preserve later edits: " + ", ".join(conflicts))
    if apply:
        with lock(root):
            restore(root, bid, False)
            for rel, data in recovery["before"].items():
                p = inside(root, rel)
                if data is None:
                    p.unlink(missing_ok=True)
                else:
                    atomic_bytes(p, bytes.fromhex(data))
            pending = root / '.artifacts/install.pending.json'
            if pending.exists() and read(pending).get('backup') == bid:
                pending.unlink()
    return {"status": "restored" if apply else "preview", "files": list(recovery["before"])}


def main():
    ap = argparse.ArgumentParser(description="JX project checks: local evidence, explicit limitations")
    ap.add_argument("--version", action="version", version=__version__)
    ap.add_argument("--root", type=Path, default=Path.cwd())
    sub = ap.add_subparsers(dest="command", required=True)
    for name in ("init", "upgrade"):
        p = sub.add_parser(name)
        p.add_argument("--manifest", required=True)
        g = p.add_mutually_exclusive_group(required=True)
        g.add_argument("--apply", action="store_true")
        g.add_argument("--dry-run", action="store_true")
    sub.add_parser("doctor")
    for name in ("verify", "finish", "task"):
        p = sub.add_parser(name)
        p.add_argument("--task", required=True)
        if name == "task":
            p.add_argument("--spec", required=True)
            p.add_argument("--scope", nargs="+", required=True)
            p.add_argument("--apply", action="store_true")
    p = sub.add_parser("restore")
    p.add_argument("--backup", required=True)
    p.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    root = args.root.resolve()
    try:
        if args.command in {"init", "upgrade"}:
            result = installation(root, args.manifest, args.apply, args.command == "upgrade")
        elif args.command == "task":
            result = capture_task(root, args.task, args.spec, args.scope, args.apply)
        elif args.command == "restore":
            result = restore(root, args.backup, args.apply)
        else:
            result = {"doctor": lambda: doctor(root), "verify": lambda: verify(root, args.task), "finish": lambda: finish(root, args.task)}[args.command]()
    except (Invalid, OSError, ValueError, KeyError, TypeError) as e:
        result = {"status": "blocked", "reason": str(e)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result["status"] in {"ok", "ready", "preview", "applied", "captured", "restored"} else 2)
