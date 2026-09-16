"""Local stand-in for the checks CI would run.

hassfest and the HACS action run on GitHub; this approximates the parts of
them that can be checked with no network at all, plus the cross-file
consistency that nothing else checks: the vendored core files against their
recorded upstream hashes, translation keys against icons and names, exceptions
raised against exceptions declared, user-facing exceptions raised without a
translation key, the manifest's published URLs against private address space,
the brand images against their required pixel sizes, the version fields
against each other, the quality scale against the pinned rule list, and every
rule marked `done` against the file set that would have to exist for it to be
true. Run it before a push so the push is not the first verification.

    python tools/validate_local.py
"""

from __future__ import annotations

import ast
import hashlib
import ipaddress
import json
import os
import re
import sys
from typing import Any

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
DOMAIN = "sleepiq_massage"
COMP = os.path.join(ROOT, "custom_components", DOMAIN)
BASELINE = os.path.join(ROOT, "docs", "UPSTREAM-BASELINE.txt")
PLATFORMS = ("binary_sensor", "button", "light", "number", "select", "sensor", "switch")

# hassfest requires these for a custom integration.
REQUIRED_MANIFEST = [
    "domain",
    "name",
    "documentation",
    "codeowners",
    "iot_class",
    "version",
]
VALID_IOT_CLASS = {
    "assumed_state",
    "cloud_polling",
    "cloud_push",
    "local_polling",
    "local_push",
    "calculated",
}

# Manifest keys whose value is a URL a stranger has to be able to open. A
# forge URL on the house LAN passes every syntactic check and reaches nobody
# outside the house, so the address family is checked, not the spelling.
MANIFEST_URL_KEYS = ("documentation", "issue_tracker")

# Home Assistant serves these from custom_components/<domain>/brand/ at
# /api/brands/integration/<domain>/<file>.
BRAND_SIZES = {
    "icon.png": (256, 256),
    "icon@2x.png": (512, 512),
    "logo.png": (512, 256),
    "logo@2x.png": (1024, 512),
}

# Pinned from developers.home-assistant.io/docs/core/integration-quality-scale/checklist
# (checked 2026-09-02: 54 rules, none new or deprecated). The list is pinned
# here on purpose: a quality_scale.yaml that is missing a rule reads as
# complete, and checking against the full list turns an omission into a
# failure.
ALL_RULES = {
    # Bronze
    "action-setup",
    "appropriate-polling",
    "brands",
    "common-modules",
    "config-flow-test-coverage",
    "config-flow",
    "dependency-transparency",
    "docs-actions",
    "docs-conditions",
    "docs-high-level-description",
    "docs-installation-instructions",
    "docs-removal-instructions",
    "docs-triggers",
    "entity-event-setup",
    "entity-unique-id",
    "has-entity-name",
    "runtime-data",
    "test-before-configure",
    "test-before-setup",
    "unique-config-entry",
    # Silver
    "action-exceptions",
    "config-entry-unloading",
    "docs-configuration-parameters",
    "docs-installation-parameters",
    "entity-unavailable",
    "integration-owner",
    "log-when-unavailable",
    "parallel-updates",
    "reauthentication-flow",
    "test-coverage",
    # Gold
    "devices",
    "diagnostics",
    "discovery-update-info",
    "discovery",
    "docs-data-update",
    "docs-examples",
    "docs-known-limitations",
    "docs-supported-devices",
    "docs-supported-functions",
    "docs-troubleshooting",
    "docs-use-cases",
    "dynamic-devices",
    "entity-category",
    "entity-device-class",
    "entity-disabled-by-default",
    "entity-translations",
    "exception-translations",
    "icon-translations",
    "reconfiguration-flow",
    "repair-issues",
    "stale-devices",
    # Platinum
    "async-dependency",
    "inject-websession",
    "strict-typing",
}

failures: list[str] = []
notes: list[str] = []


def read(*parts: str) -> str:
    with open(os.path.join(*parts), encoding="utf-8") as fh:
        return fh.read()


def read_json(*parts: str) -> Any:
    return json.loads(read(*parts))


def check(condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def constants(source: str, prefix: str) -> dict[str, str]:
    """Module-level string assignments whose name starts with prefix."""
    found: dict[str, str] = {}
    for node in ast.parse(source).body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if (
            isinstance(target, ast.Name)
            and target.id.startswith(prefix)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            found[target.id] = node.value.value
    return found


# Every exception a user can see on the integration card or in an action
# error. A raise of one of these without translation_key shows an English
# f-string to every user, whatever their language.
TRANSLATED_EXCEPTIONS = {
    "HomeAssistantError",
    "ServiceValidationError",
    "ConfigEntryNotReady",
    "ConfigEntryAuthFailed",
    "ConfigEntryError",
    "UpdateFailed",
}


def untranslated_raises(source: str, filename: str) -> list[str]:
    """Raises of Home Assistant's user-facing exceptions that carry no key."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Raise) or not isinstance(node.exc, ast.Call):
            continue
        func = node.exc.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
        if name not in TRANSLATED_EXCEPTIONS:
            continue
        keywords = {kw.arg for kw in node.exc.keywords}
        if "translation_key" not in keywords:
            found.append(
                f"{filename}:{node.lineno} raises {name} without translation_key"
            )
    return found


def pyproject_version() -> str | None:
    """The version in pyproject.toml, or None when the file does not carry one."""
    path = os.path.join(ROOT, "pyproject.toml")
    if not os.path.isfile(path):
        return None
    import tomllib

    with open(path, "rb") as fh:
        project = tomllib.load(fh).get("project", {})
    version = project.get("version")
    return str(version) if version is not None else None


def baseline() -> tuple[dict[str, str], set[str]]:
    """Upstream hashes by file name, and the names this project modifies.

    docs/UPSTREAM-BASELINE.txt is the single record of both: a line ending in
    `modified` is a file this project edits on purpose, and NOTICE describes
    how. Every other file must still match core byte for byte.
    """
    hashes: dict[str, str] = {}
    modified: set[str] = set()
    for line in read(BASELINE).splitlines():
        match = re.match(r"\s*([0-9a-f]{64})\s+\*?(\S+)(\s+modified)?\s*$", line)
        if not match:
            continue
        hashes[match.group(2)] = match.group(1)
        if match.group(3):
            modified.add(match.group(2))
    return hashes, modified


def brand_faults() -> list[str]:
    """Brand files that are absent or the wrong size, one string each.

    HACS requires the brand directory of a custom integration; the store shows
    a grey box when a file is missing, with no error anywhere. The pixel sizes
    are checked here rather than trusted from tools/make_brand.py, which is
    what wrote them.
    """
    faults = []
    for name, want in BRAND_SIZES.items():
        path = os.path.join(COMP, "brand", name)
        if not os.path.isfile(path):
            faults.append(f"brand/{name} is missing")
            continue
        try:
            from PIL import Image
        except ImportError:
            notes.append("Pillow not installed - brand image sizes not measured")
            return faults
        with Image.open(path) as image:
            size = image.size
        if size != want:
            faults.append(
                f"brand/{name} is {size[0]}x{size[1]}, want {want[0]}x{want[1]}"
            )
    return faults


def missing_evidence(manifest: dict[str, Any]) -> dict[str, str]:
    """Rules whose mechanism is not in the files, with what is missing.

    Only the rules that leave a mark a script can see are listed here; the
    rest are judgement and live in the yaml's comments. A rule in this dict
    may not be filed `done`.
    """
    component = {
        f: read(COMP, f) for f in sorted(os.listdir(COMP)) if f.endswith(".py")
    }
    everything = "\n".join(component.values())
    flow = component["config_flow.py"]
    coordinator = component["coordinator.py"]
    tests_workflow = read(ROOT, ".github", "workflows", "tests.yml")
    pyproject = read(ROOT, "pyproject.toml")

    missing: dict[str, str] = {}

    def want(rule: str, ok: bool, message: str) -> None:
        if not ok:
            missing[rule] = message

    want(
        "brands",
        not brand_faults(),
        "; ".join(brand_faults()),
    )
    want(
        "discovery",
        not set(manifest) & {"dhcp", "zeroconf", "ssdp", "bluetooth", "usb"}
        or any(f"async_step_{k}" in flow for k in ("dhcp", "zeroconf", "ssdp", "usb")),
        "the manifest matches a discovery but the flow has no step for it",
    )
    want(
        "reconfiguration-flow",
        "async_step_reconfigure" in flow,
        "config_flow.py has no async_step_reconfigure",
    )
    want(
        "reauthentication-flow",
        "async_step_reauth" in flow,
        "config_flow.py has no async_step_reauth",
    )
    want(
        "repair-issues",
        "async_create_issue" in everything,
        "nothing raises a repair issue",
    )
    want(
        "dynamic-devices",
        "async_add_listener" in everything,
        "no platform listens for devices added after setup",
    )
    want(
        "stale-devices",
        "async_remove_device" in coordinator
        or "async_remove_config_entry_device" in everything,
        "nothing removes a device that has left the account",
    )
    want(
        "diagnostics",
        os.path.isfile(os.path.join(COMP, "diagnostics.py")),
        "there is no diagnostics.py",
    )
    want(
        "has-entity-name",
        "_attr_has_entity_name = True" in everything,
        "no entity sets _attr_has_entity_name",
    )
    want(
        "entity-unique-id",
        "sleeper_for_side" not in everything
        and "_async_migrate_side_keyed_unique_ids" in component["__init__.py"],
        "a unique id falls back to the first sleeper, which collides on a bed "
        "where only one side has one, or the migration off that key is gone",
    )
    want(
        "icon-translations",
        os.path.isfile(os.path.join(COMP, "icons.json"))
        and "_attr_icon" not in everything,
        "icons.json is missing or an _attr_icon overrides it",
    )
    want(
        "parallel-updates",
        all("PARALLEL_UPDATES" in component[f"{p}.py"] for p in PLATFORMS),
        "a platform does not set PARALLEL_UPDATES",
    )
    want(
        "test-coverage",
        "--cov-fail-under=95" in tests_workflow,
        "the Tests workflow does not gate coverage at 95%",
    )
    want(
        "strict-typing",
        "strict = true" in pyproject and "\nimplicit_reexport" not in pyproject,
        "mypy is not strict, or a module override re-allows implicit re-export",
    )
    return missing


REPO_ALLOWED_HOSTS = frozenset(
    {
        "10.0.0.5",  # a bed gateway address in tests/ha/test_config_flow.py
        "192.168.0.5",  # a bed gateway address in tests/ha/test_massage_entities.py
    }
)


# ------------------------------------------------- development-host refusal
# hassfest and the HACS action read the manifest and nothing else, so a
# development address anywhere in the tree - a workflow comment, a README, a
# docstring - ships with every check green. Two rules, one strict and one
# narrower: the manifest URLs are refused for anything a user cannot open,
# and every published file is refused for anything that names this network.
import subprocess as _subprocess  # noqa: E402
from urllib.parse import urlsplit as _urlsplit  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _netblocks  # noqa: E402

MANIFEST_NETS = tuple(
    ipaddress.ip_network(c)
    for c in _netblocks.TREE_CIDRS + _netblocks.MANIFEST_ONLY_CIDRS
)
TREE_NETS = tuple(ipaddress.ip_network(c) for c in _netblocks.TREE_CIDRS)
MANIFEST_ONLY_NAMES = ("localhost",)
PRIVATE_SUFFIXES = _netblocks.PRIVATE_SUFFIXES

# Hosts that look like a development host and are not one. Every entry is
# load-bearing in this repository and carries the reason on its line; an
# entry added without one is how the rule stops working.
ALLOWED_HOSTS = frozenset(
    {
        "homeassistant.local",  # the default Home Assistant address, in every install doc
    }
    | REPO_ALLOWED_HOSTS
)

# Text that ships to whoever clones or installs the repository. The file list
# comes from git rather than a walk: git already knows what is ignored, which
# is how private operational notes under an ignored directory stay out, and
# --others adds a file created for this commit and not yet staged.
PUBLISHED_SUFFIXES = {
    ".cfg",
    ".ini",
    ".json",
    ".md",
    ".py",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
PUBLISHED_NAMES = {
    ".gitattributes",
    ".gitignore",
    "CODEOWNERS",
    "LICENSE",
    "NOTICE",
}
# The one published file the scan skips: it holds the CIDRs the scan matches
# on, so it would report itself. Nothing else may live in it.
SCAN_EXEMPT = ("tools/_netblocks.py",)

IP_LITERAL_RE = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
URL_RE = re.compile(r"\b[a-zA-Z][a-zA-Z0-9+.\-]*://[^\s\"'`<>)\]},]+")
# A host written in prose with no scheme. The suffix must end the name:
# \b would match the "home" of home-assistant.io.
BARE_HOST_RE = re.compile(
    r"(?<![\w.-])(?:[a-z0-9][a-z0-9-]*\.)+"
    r"(?:corp|home|home\.arpa|intranet|internal|lan|local|localdomain)(?![\w-])",
    re.IGNORECASE,
)
# A host made of anything else is a template - f"http://{host}/" - not a host.
HOST_CHARS_RE = re.compile(r"^[a-z0-9.\-\[\]:]+$", re.IGNORECASE)


def is_netmask(text: str) -> bool:
    """A dotted quad written as a contiguous subnet mask, 255.255.255.0 and up.

    Every such mask sits in the top reserved block and would otherwise be
    refused as a reserved address. The all-zero mask is a mask too, and is
    deliberately not exempt: as a host it is the unspecified address.
    """
    if not text.startswith("255."):
        return False
    try:
        value = int(ipaddress.IPv4Address(text))
    except ipaddress.AddressValueError:
        return False
    inverted = (~value) & 0xFFFFFFFF
    return inverted & (inverted + 1) == 0


def blocked_address(text: str, nets: tuple[Any, ...]) -> bool:
    """Whether text is an address literal inside one of nets."""
    if is_netmask(text):
        return False
    try:
        address = ipaddress.ip_address(text)
    except ValueError:
        return False
    return any(address in net for net in nets)


def blocked_host(host: str, nets: tuple[Any, ...], names: tuple[str, ...] = ()) -> bool:
    """Whether a hostname resolves or routes inside one network only.

    `names` are hosts refused by spelling rather than by address family. Only
    the manifest rule passes any: "localhost" names no machine on this
    network, so it is a dead documentation link but not a disclosure.
    """
    host = host.strip().rstrip(".").lower()
    if not host or host in ALLOWED_HOSTS:
        return False
    if host in names:
        return True
    if blocked_address(host, nets):
        return True
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        # A literal outside nets is a public address, whatever its shape.
        return False
    if host.endswith(PRIVATE_SUFFIXES):
        return True
    # A name with no dot is resolved against whatever search domain the reader
    # happens to have, so it names a machine on a LAN rather than on the net.
    return "." not in host


def unreachable_host(url: str) -> str | None:
    """The host of a manifest URL no user outside this network can open."""
    if not isinstance(url, str) or not url:
        return None
    try:
        host = _urlsplit(url).hostname or ""
    except ValueError:
        return None
    if host and not HOST_CHARS_RE.match(host):
        return None
    return host if blocked_host(host, MANIFEST_NETS, MANIFEST_ONLY_NAMES) else None


def malformed_url(url: Any) -> bool:
    """A manifest URL that is not an absolute http(s) URL with a host.

    unreachable_host answers with a host or None, and "not-a-url" has no host
    to report.
    """
    if not isinstance(url, str) or not url:
        return True
    try:
        parts = _urlsplit(url)
    except ValueError:
        return True
    return parts.scheme not in {"http", "https"} or not parts.hostname


def published_files() -> list[str]:
    """Every text file that ships, relative to ROOT, from git's own index.

    Falls back to a walk when git is not there - an extracted tarball - so the
    rule still runs, and says so, rather than passing on an empty list.
    """
    paths: list[str] = []
    try:
        listing = _subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, _subprocess.SubprocessError):
        listing = None
    if listing is not None and listing.returncode == 0:
        paths = [p for p in listing.stdout.split("\0") if p]
    else:
        notes.append("git not available - the tree scan walked the directory instead")
        for dirpath, dirs, files in os.walk(ROOT):
            dirs[:] = [
                d
                for d in dirs
                if d not in {"__pycache__", "venv", "htmlcov", "node_modules"}
                and not (d.startswith(".") and d not in {".gitea", ".github"})
            ]
            for f in files:
                paths.append(
                    os.path.relpath(os.path.join(dirpath, f), ROOT).replace("\\", "/")
                )
    keep: list[str] = []
    for path in paths:
        if path in SCAN_EXEMPT:
            continue
        name = path.rsplit("/", 1)[-1]
        if (
            os.path.splitext(name)[1].lower() in PUBLISHED_SUFFIXES
            or name in PUBLISHED_NAMES
        ):
            keep.append(path)
    return sorted(keep)


def tree_hits(text: str, name_re: Any = None) -> list[tuple[int, str]]:
    """Every development host named in text, as (line number, host)."""
    hits: list[tuple[int, str]] = []
    for number, line in enumerate(text.splitlines(), 1):
        if name_re is not None:
            for name in name_re.findall(line):
                if name.lower() not in ALLOWED_HOSTS:
                    hits.append((number, name.lower()))
        for literal in IP_LITERAL_RE.findall(line):
            if literal not in ALLOWED_HOSTS and blocked_address(literal, TREE_NETS):
                hits.append((number, literal))
        for url in URL_RE.findall(line):
            try:
                host = _urlsplit(url).hostname or ""
            except ValueError:
                continue
            if not host or not HOST_CHARS_RE.match(host):
                continue
            if blocked_host(host, TREE_NETS):
                hits.append((number, host))
        for name in BARE_HOST_RE.findall(line):
            if name.lower() not in ALLOWED_HOSTS:
                hits.append((number, name.lower()))
    return hits


def scan_published_tree() -> None:
    """Refuse a development host anywhere in the published tree."""
    exempt = os.path.join(ROOT, *SCAN_EXEMPT[0].split("/"))
    if os.path.isfile(exempt):
        allowed_names = {"TREE_CIDRS", "MANIFEST_ONLY_CIDRS", "PRIVATE_SUFFIXES"}
        for node in ast.parse(read(exempt)).body:
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                continue
            if isinstance(node, ast.ImportFrom) and node.module == "__future__":
                continue
            targets = node.targets if isinstance(node, ast.Assign) else []
            if not all(
                isinstance(t, ast.Name) and t.id in allowed_names for t in targets
            ):
                failures.append(
                    f"{SCAN_EXEMPT[0]} holds more than the pinned address space; "
                    "the tree scan skips this file, so nothing else may live in it"
                )
                break
    # A repository that knows its own development host names - read from
    # outside the tree, because naming them in a published file is the
    # disclosure this rule exists to prevent - has them matched as well.
    name_re = None
    finder = globals().get("internal_names")
    if callable(finder):
        names = finder()
        if names:
            name_re = re.compile(
                r"\b(?:" + "|".join(re.escape(n) for n in names) + r")\w*",
                re.IGNORECASE,
            )
            notes.append(f"{len(names)} development host names given to the tree scan")
        else:
            notes.append("no development host names given to the tree scan")
    seen = 0
    for path in published_files():
        full = os.path.join(ROOT, *path.split("/"))
        if not os.path.isfile(full):
            continue
        try:
            text = read(full)
        except (OSError, UnicodeDecodeError):
            continue
        seen += 1
        for number, host in tree_hits(text, name_re):
            failures.append(
                f"{path}:{number} names {host} - that host is on the development "
                "network and means nothing to a user who installs this"
            )
    check(seen > 0, "the published-tree scan read no files, so it proved nothing")


def main() -> int:
    manifest = read_json(COMP, "manifest.json")
    const_src = read(COMP, "const.py")
    strings = read_json(COMP, "strings.json")

    # ---------------------------------------------------------- manifest
    for key in REQUIRED_MANIFEST:
        check(key in manifest, f"manifest.json missing required key {key!r}")
    check(
        manifest.get("domain") == DOMAIN,
        f"manifest domain is {manifest.get('domain')!r}",
    )
    check(
        manifest.get("iot_class") in VALID_IOT_CLASS,
        f"manifest iot_class {manifest.get('iot_class')!r} is not a valid value",
    )
    check(
        isinstance(manifest.get("codeowners"), list)
        and all(c.startswith("@") for c in manifest["codeowners"]),
        "manifest codeowners entries must start with @",
    )
    for key in MANIFEST_URL_KEYS:
        url = manifest.get(key)
        if not isinstance(url, str):
            continue
        host = unreachable_host(url)
        check(
            host is None,
            f"manifest {key} host {host!r} is not reachable from outside this "
            f"network - publish the URL a user can open",
        )
    keys = list(manifest)
    check(
        keys[:2] == ["domain", "name"] and keys[2:] == sorted(keys[2:]),
        "manifest keys must be domain, name, then alphabetical (hassfest MANIFEST)",
    )
    check(
        "quality_scale" not in manifest,
        "quality_scale in manifest.json: the badge is core-only, a custom "
        "integration builds to the rules and does not claim a tier",
    )
    # A custom integration without a version silently fails to load - the
    # symptom is a missing integration, not an error.
    check(bool(manifest.get("version")), "manifest version is empty")
    project_version = pyproject_version()
    if project_version is not None:
        check(
            project_version == manifest.get("version"),
            f"pyproject version {project_version!r} != manifest version "
            f"{manifest.get('version')!r} - bump them together",
        )

    # ---------------------------------------------------------- hacs.json
    hacs = read_json(ROOT, "hacs.json")
    check("name" in hacs, "hacs.json must contain name")

    # ------------------------------------------------------ vendored files
    # The point of the baseline: an upstream resync stays a small diff only
    # while the untouched files stay byte-identical. Reformatting one - by
    # ruff --fix, an editor, or a well-meaning cleanup - silently destroys
    # that, and nothing else would notice.
    hashes, modified = baseline()
    check(bool(hashes), "docs/UPSTREAM-BASELINE.txt lists no files")
    for name, want in sorted(hashes.items()):
        path = os.path.join(COMP, name)
        if not os.path.isfile(path):
            failures.append(f"{name}: in the baseline but missing from the component")
            continue
        with open(path, "rb") as fh:
            got = hashlib.sha256(fh.read()).hexdigest()
        if name in modified:
            check(
                got != want,
                f"{name}: marked modified in the baseline but identical to upstream",
            )
        else:
            check(
                got == want,
                f"{name}: drifted from upstream - mark it modified or restore it",
            )
    notice = read(ROOT, "NOTICE")
    for name in sorted(modified):
        check(name in notice, f"{name}: modified but NOTICE does not describe how")

    # ---------------------------------------------------------- translations
    # Home Assistant reads translations/<lang>.json at runtime; strings.json is
    # only hassfest's input. Both must exist and agree, and neither may carry
    # core's [%key:...] references, which resolve only inside core's build.
    en = read_json(COMP, "translations", "en.json")
    check(
        strings == en,
        "strings.json and translations/en.json differ - copy strings.json over",
    )
    for name in ("strings.json", os.path.join("translations", "en.json")):
        check(
            "%key:" not in read(COMP, name),
            f"{name}: core-only [%key:...] reference - replace with a literal",
        )
    for f in sorted(os.listdir(os.path.join(COMP, "translations"))):
        check(f.endswith(".json"), f"translations/{f} is not a JSON file")

    # ---------------------------------------------------------- quality scale
    scale_path = os.path.join(COMP, "quality_scale.yaml")
    check(os.path.isfile(scale_path), "quality_scale.yaml is missing")
    if os.path.isfile(scale_path):
        try:
            import yaml

            declared = yaml.safe_load(read(scale_path)).get("rules", {})
            missing = ALL_RULES - set(declared)
            check(not missing, f"quality_scale.yaml does not mention {sorted(missing)}")
            unknown = set(declared) - ALL_RULES
            check(not unknown, f"quality_scale.yaml invents rules {sorted(unknown)}")
            for rule, value in sorted(declared.items()):
                if isinstance(value, dict):
                    check(
                        value.get("status") in {"done", "todo", "exempt"},
                        f"{rule}: status must be done/todo/exempt",
                    )
                    if value.get("status") != "done":
                        check(
                            bool(str(value.get("comment", "")).strip()),
                            f"{rule}: a non-done status needs a comment saying why",
                        )
                else:
                    check(value == "done", f"{rule}: bare value must be 'done'")
            todo = sorted(
                r
                for r, v in declared.items()
                if isinstance(v, dict) and v.get("status") == "todo"
            )
            if todo:
                notes.append(f"quality scale still todo: {', '.join(todo)}")

            # A rule filed `done` has to be visible in the files. This is the
            # check that stops the yaml drifting back into a claim: it fails
            # when a rule says done and the mechanism it needs is absent.
            for rule, message in sorted(missing_evidence(manifest).items()):
                status = declared.get(rule)
                status = status.get("status") if isinstance(status, dict) else status
                check(status != "done", f"{rule}: filed done but {message}")
        except ImportError:
            notes.append("PyYAML not installed - quality_scale.yaml not parsed")

    # ------------------------------------------ entity and icon translations
    # Every entity in this integration is named from strings.json through a
    # translation key, so: no key may be declared that no platform mentions,
    # and every key a platform mentions must have a name. Keys reach a platform
    # three ways - a literal, a constant imported from const.py, and a lookup
    # table - so a key counts as used when the platform's source contains the
    # literal or names the constant that holds it.
    icons = read_json(COMP, "icons.json")
    exc_re = re.compile(r'translation_domain=DOMAIN,\s*translation_key="([^"]+)"')
    const_values = constants(const_src, "")
    for platform in PLATFORMS:
        source = read(COMP, f"{platform}.py")
        used = {
            node.value
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        used -= set(exc_re.findall(source))
        used |= {v for k, v in const_values.items() if k in source}
        declared_icons = set(icons.get("entity", {}).get(platform, {}))
        named = set(strings.get("entity", {}).get(platform, {}))
        check(
            declared_icons <= used,
            f"{platform}: icons.json has unused keys {sorted(declared_icons - used)}",
        )
        check(
            named <= used,
            f"{platform}: strings.json has unused keys {sorted(named - used)}",
        )
        for key in sorted(declared_icons | named):
            check(
                bool(
                    strings.get("entity", {}).get(platform, {}).get(key, {}).get("name")
                ),
                f"{platform}: {key} has no translated name in strings.json",
            )

    # ------------------------------------------------- exception translations
    # Two checks: every key raised is declared (and vice versa), and no
    # user-facing exception is raised without a key anywhere in the
    # component - setup and poll failures in __init__.py and coordinator.py
    # included, since those show on the integration card.
    raised: set[str] = set()
    literals: set[str] = set()
    for f in sorted(os.listdir(COMP)):
        if f.endswith(".py"):
            source = read(COMP, f)
            raised |= set(exc_re.findall(source))
            literals |= {
                node.value
                for node in ast.walk(ast.parse(source))
                if isinstance(node, ast.Constant) and isinstance(node.value, str)
            }
            for message in untranslated_raises(source, f):
                failures.append(message)
    declared_exc = set(strings.get("exceptions", {}))
    check(
        raised <= declared_exc,
        f"code raises undeclared exception keys {sorted(raised - declared_exc)}",
    )
    # Some keys reach the raise through the shared write helper rather than a
    # literal at the raise itself, so an unused declaration is one whose key
    # appears nowhere in the component at all.
    check(
        declared_exc <= literals,
        f"strings.json declares unused exceptions {sorted(declared_exc - literals)}",
    )

    # ----------------------------------------------------- issue translations
    issue_consts = set(constants(const_src, "ISSUE_").values())
    declared_issues = set(strings.get("issues", {}))
    check(
        issue_consts == declared_issues,
        f"const.py issues {sorted(issue_consts)} != strings.json issues "
        f"{sorted(declared_issues)}",
    )

    # ------------------------------------------------------------ platforms
    init_src = read(COMP, "__init__.py")
    for platform in PLATFORMS:
        source = read(COMP, f"{platform}.py")
        check(
            f"Platform.{platform.upper()}" in init_src,
            f"{platform}.py exists but Platform.{platform.upper()} is not forwarded",
        )
        # Every platform here is forked from core and owned, so every one of
        # them declares its own limit rather than inheriting core's omission.
        check(
            "PARALLEL_UPDATES" in source,
            f"{platform}.py does not set PARALLEL_UPDATES",
        )

    # ------------------------------------------------- naming and icon source
    # A hard-coded _attr_name defeats the translated name and a hard-coded
    # _attr_icon defeats icons.json; both were the whole point of the fork.
    for f in sorted(os.listdir(COMP)):
        if not f.endswith(".py"):
            continue
        source = read(COMP, f)
        check("_attr_name" not in source, f"{f}: sets _attr_name; name it in strings")
        check("_attr_icon" not in source, f"{f}: sets _attr_icon; put it in icons.json")
    check(
        "_attr_has_entity_name = True" in read(COMP, "entity.py"),
        "entity.py: the base classes must set _attr_has_entity_name",
    )

    # ---------------------------------------------- development-host refusal
    for _key in ("documentation", "issue_tracker"):
        if _key in manifest:
            check(
                not malformed_url(manifest.get(_key)),
                f"manifest {_key} is not an absolute http(s) URL a user can open",
            )
    scan_published_tree()

    # ---------------------------------------------------------- syntax
    for dirpath, _dirs, files in os.walk(COMP):
        for f in files:
            if f.endswith(".py"):
                path = os.path.join(dirpath, f)
                try:
                    ast.parse(read(path))
                except SyntaxError as err:
                    failures.append(f"{f}: {err}")
            elif f.endswith(".json"):
                try:
                    read_json(dirpath, f)
                except ValueError as err:
                    failures.append(f"{f}: {err}")

    # ---------------------------------------------------------- report
    print(f"manifest {manifest.get('domain')} {manifest.get('version')}")
    for n in notes:
        print(f"  NOTE   {n}")
    for f in failures:
        print(f"  FAIL   {f}")
    if not failures:
        print("  all offline checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
