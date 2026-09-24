"""Local stand-in for the checks CI would run.

hassfest and the HACS action run on GitHub; this approximates the parts of
them that can be checked with no network at all, plus the cross-file
consistency that nothing else checks: the vendored core files against their
recorded upstream hashes, translation keys against icons and names, exceptions
raised against exceptions declared, user-facing exceptions raised without a
translation key, the manifest's published URLs against private address space,
the brand images against their required pixel sizes, the version fields
against each other, the quality scale against the pinned rule list, every
rule marked `done` against the file set that would have to exist for it to be
true, every text file git ships against the development addresses, names and
infrastructure phrases those scans refuse, every blob and commit message in
the object database against the same address matchers, and git's index against
the paths a clone must never carry. Run it before a push so the push is not
the first verification.

    python tools/validate_local.py

The development host names come from `HA_DEV_HOST_NAMES` or from a file under
the user profile, outside every clone, so no clone can stage them and nothing
here asks a reader to create a file inside the tree. Off CI a run with no name
input fails, so a clean local exit means the name half ran. Under `CI` it is a
note, because no workflow supplies the names.

Observed 2026-09-16 in a clone with no name input and `CI` set: the run covers
the address literals, the URL hosts and the bare private host names, over the
published tree and over every blob and commit message in the object database,
and fires a synthetic control for each of those three rules. A development
host name written into the tree is caught by the run a maintainer makes before
pushing, and by nothing in CI.

The infrastructure phrases come from `HA_DEV_PRIVATE_PHRASES` or from a second
file under the user profile. They match prose that names private CI topology,
account structure or lab tooling without naming a host, which is a class none
of the address matchers can see. The phrase half reads the published tree
only: the object database holds commit messages of that class which no rewrite
here can reach, so a matcher over them would refuse history rather than the
next commit.

A matched string is printed locally and withheld when `CI` or
`GITHUB_ACTIONS` is set. See `disclose`.
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

# Every runner sets CI; GITHUB_ACTIONS names the one whose run log is public
# on a public repository. Either one set to anything but 0 or false withholds
# a matched string.
CI_ENV = ("CI", "GITHUB_ACTIONS")
WITHHELD = "a string withheld from this public log"


def redacting() -> bool:
    """Whether a matched string may be printed."""
    return any(
        os.environ.get(key, "").strip().lower() not in ("", "0", "false")
        for key in CI_ENV
    )


def disclose(text: str) -> str:
    """A matched host as a message writes it.

    Locally the string is the useful half: it is what the maintainer greps
    for. In CI it is the disclosure these scans exist to prevent, so the file,
    the line and the rule that fired are kept and the text is dropped. The
    environment decides rather than a flag, because a workflow that forgets to
    pass a flag would publish the string. Nothing derived from the text is
    printed either: a truncated digest of a short host name is confirmable
    against a candidate list, so it discloses what it summarises. Actions
    masks a registered secret's exact value and the name matcher deliberately
    matches a longer word, so the string reaching a log is the one masking
    misses.
    """
    return WITHHELD if redacting() else text


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
        "10.0.0.6",  # a second bed's address in tests/ha/test_config_flow.py
        "192.168.0.5",  # a bed gateway address in tests/ha/test_massage_entities.py
        # The object scan reads commit messages, and a message that records
        # which ranges this rule refuses names them. These three are the ones
        # it quotes. Each names a range or a vendor default, never a machine.
        "100.64.0.0",  # the CGNAT network address, quoted in the rule's own history
        "192.168.1.254",  # the AT&T gateway factory default, public product documentation
        "10.0.0.3",  # a synthetic address a commit message uses as its example
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

# Development host names are matched as well as addresses, and they cannot be
# listed here: naming them in a published file is the disclosure this rule
# exists to prevent. The environment or a file under the user profile carries
# them in from outside every clone. An in-tree fallback path was the previous
# design and is not usable: git ignores it only through .git/info/exclude,
# which no clone receives, so the file the fallback asked for became a staged
# file and a scan failure everywhere but the machine that wrote the exclude.
DEV_HOST_ENV = "HA_DEV_HOST_NAMES"
DEV_HOST_FILE = "~/.config/ha-dev-hosts.txt"
DEV_PHRASE_ENV = "HA_DEV_PRIVATE_PHRASES"
DEV_PHRASE_FILE = "~/.config/ha-dev-phrases.txt"


def outside_input(env: str, fallback: str) -> str:
    """The raw contents of one out-of-tree input, or an empty string.

    The variable holds the values directly or holds the path of a file listing
    them, one per line with `#` starting a comment. With the variable unset the
    fallback path under the user profile is read in the file form.
    """
    raw = os.environ.get(env, "").strip()
    if not raw:
        expanded = os.path.expanduser(fallback)
        raw = expanded if os.path.isfile(expanded) else ""
    if not raw:
        return ""
    if os.path.isfile(raw):
        return "\n".join(line.split("#", 1)[0] for line in read(raw).splitlines())
    return raw


def internal_names() -> list[str]:
    """Development host names for the scans to refuse.

    Each name matches with any trailing word characters, so a bare name also
    catches the same name with a role or a number appended. No example name is
    written here: this file is scanned too, and a literal example is a hit the
    moment someone supplies that name.
    """
    raw = outside_input(DEV_HOST_ENV, DEV_HOST_FILE)
    return sorted({n.strip().lower() for n in re.split(r"[,\s]+", raw) if n.strip()})


def internal_phrases() -> list[str]:
    """Infrastructure phrases for the tree scan to refuse.

    One phrase per line, matched case-insensitively as a substring, because a
    phrase of this class is prose rather than a token. Newline separated only:
    a phrase holds spaces and commas.
    """
    raw = outside_input(DEV_PHRASE_ENV, DEV_PHRASE_FILE)
    return sorted({p.strip().lower() for p in raw.splitlines() if p.strip()})


def name_matcher(names: list[str]) -> Any:
    """A regex matching any of names with any suffix. None when given none."""
    if not names:
        return None
    return re.compile(
        r"\b(?:" + "|".join(re.escape(n) for n in names) + r")\w*",
        re.IGNORECASE,
    )


# Text that ships to whoever clones or installs the repository. The file list
# comes from git rather than a walk: git already knows what is ignored, which
# is how private operational notes under an ignored directory stay out, and
# --others adds a file created for this commit and not yet staged.
PUBLISHED_SUFFIXES = {
    ".cfg",
    ".html",
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
# A directory of maintainer notes that no clone carries. The scan neither
# reads it nor names it in a failure, so a run in an extracted tree with the
# notes beside it reports on the repository rather than on the notes. A file
# under it reaching the index is refused by refuse_unpublished_paths instead.
SCAN_SKIP_PREFIXES = ("docs/local/",)
# Paths that belong to a working copy and not to a clone. Each one is either
# maintainer instructions or session configuration, and .gitignore cannot
# carry the rule: the ignore file ships, so its rules describe what they hide.
# This check travels with the tree the way an ignore rule does not.
UNPUBLISHED_PATHS = (
    ".claude/",
    ".cursorrules",
    "AGENTS.md",
    "CLAUDE.md",
    "docs/local/",
)

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

# Which matcher produced a hit. A message carries this whether or not it
# carries the matched string.
RULE_NAME = "development host name"
RULE_ADDRESS = "private address literal"
RULE_URL = "private URL host"
RULE_SUFFIX = "private domain suffix"
RULE_PHRASE = "private infrastructure phrase"


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
    rule still runs, and says so, rather than passing on an empty list. The
    walk honours no ignore rule, so SCAN_SKIP_PREFIXES does the skipping that
    git would have done in either branch.
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
    except OSError, _subprocess.SubprocessError:
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
        if path in SCAN_EXEMPT or path.startswith(SCAN_SKIP_PREFIXES):
            continue
        name = path.rsplit("/", 1)[-1]
        if (
            os.path.splitext(name)[1].lower() in PUBLISHED_SUFFIXES
            or name in PUBLISHED_NAMES
        ):
            keep.append(path)
    return sorted(keep)


def tree_hits(
    text: str, name_re: Any = None, phrases: tuple[str, ...] = ()
) -> list[tuple[int, str, str]]:
    """Every development host named in text, as (line number, host, rule).

    The rule is carried out with the hit because it is what a message says
    when the matched host itself is withheld. `phrases` are passed by the tree
    scan only; scan_object_database passes none.
    """
    hits: list[tuple[int, str, str]] = []
    for number, line in enumerate(text.splitlines(), 1):
        lowered = line.lower()
        for phrase in phrases:
            if phrase in lowered:
                hits.append((number, phrase, RULE_PHRASE))
        if name_re is not None:
            for name in name_re.findall(line):
                if name.lower() not in ALLOWED_HOSTS:
                    hits.append((number, name.lower(), RULE_NAME))
        for literal in IP_LITERAL_RE.findall(line):
            if literal not in ALLOWED_HOSTS and blocked_address(literal, TREE_NETS):
                hits.append((number, literal, RULE_ADDRESS))
        for url in URL_RE.findall(line):
            try:
                host = _urlsplit(url).hostname or ""
            except ValueError:
                continue
            if not host or not HOST_CHARS_RE.match(host):
                continue
            if blocked_host(host, TREE_NETS):
                hits.append((number, host, RULE_URL))
        for name in BARE_HOST_RE.findall(line):
            if name.lower() not in ALLOWED_HOSTS:
                hits.append((number, name.lower(), RULE_SUFFIX))
    return hits


def fired(
    rule: str, text: str, name_re: Any = None, phrases: tuple[str, ...] = ()
) -> bool:
    """Whether one named rule produced a hit on text.

    The rule is checked rather than the hit list: a control line for the URL
    rule carries an address literal too, so a non-empty list proves only that
    some matcher fired.
    """
    return any(r == rule for _n, _h, r in tree_hits(text, name_re, phrases))


def scan_controls(
    names: list[str], name_re: Any, phrases: tuple[str, ...] = ()
) -> None:
    """Fire every live matcher on synthetic input before a clean scan is believed.

    A tree holding nothing and a matcher matching nothing print the same
    result. The control lines are built here and never written to a file. One
    control per rule: neutering a single matcher left the run green on two of
    the three rules the CI run relies on before these were added.
    """
    address = str(next(n for n in TREE_NETS if n.version == 4).network_address + 1)
    check(
        fired(RULE_ADDRESS, f"control line naming {address}"),
        f"the {RULE_ADDRESS} rule did not match {disclose(address)}, an "
        "address it refuses, so a clean scan says nothing about the addresses "
        "in this repository",
    )
    check(
        fired(RULE_URL, f"control line naming http://{address}:3000/x"),
        f"the {RULE_URL} rule did not match a URL on {disclose(address)}, a "
        "host it refuses, so a clean scan says nothing about the URLs in this "
        "repository",
    )
    suffix_host = "control-line" + PRIVATE_SUFFIXES[0]
    check(
        fired(RULE_SUFFIX, f"control line naming {suffix_host}"),
        f"the {RULE_SUFFIX} rule did not match {suffix_host}, a name it "
        "refuses, so a clean scan says nothing about the private suffixes in "
        "this repository",
    )
    if phrases:
        check(
            fired(RULE_PHRASE, f"control line quoting {phrases[0]}", None, phrases),
            f"the {RULE_PHRASE} rule did not match {disclose(phrases[0])}, a "
            "phrase it was given, so a clean scan says nothing about the "
            "phrases in this repository",
        )
    if not names:
        return
    check(
        fired(RULE_NAME, f"control line naming {names[0]}-ci", name_re),
        f"the {RULE_NAME} rule did not match {disclose(names[0])}, a name it "
        "was given, so a clean scan says nothing about the names in this "
        "repository",
    )


# ------------------------------------------------- object-database refusal
# published_files() reads the index, so the tree scan cannot see an object no
# ref reaches. A force-push replaces the branch and leaves the objects behind,
# and a forge serves an unreachable commit by its SHA, so an orphan is
# published while every HEAD-scoped and ref-scoped check reports clean. This
# pass runs the same address matchers over every blob and commit message in
# the object database.
#
# The pass is scoped to the objects this database holds. A CI checkout holds
# the objects its refs reach and no orphan, so the orphan case is caught in a
# clone of the forge or in the forge's own object database and not in CI.
# Measured 2026-09-16 at 54a58db: the authoring clone reads 365 objects and
# refuses 8 that no ref reaches, and a clone of the same HEAD over the git
# transport reads 326 and refuses none.
#
# Objects whose hits are the pinned address table itself, by SHA and reason.
# A version of tools/_netblocks.py is exempt by its name in the tree instead,
# so a later edit to that file needs no entry here. Every entry here is a
# commit message: an exemption by SHA blinds the whole object, so a host-scoped
# entry in REPO_ALLOWED_HOSTS is preferred wherever the hit is an address a
# file may hold.
SCAN_EXEMPT_OBJECTS = {
    # commit message stating the CIDRs the tree scan pins, plus one gateway
    # address inside one of them that the measurement it records used
    "10e8e867df6cb1d41b76ef236a496dcaa5092afe": "development-host refusal",
    # commit message stating the CIDRs the manifest URL rule pins
    "e3892ca20b494039a6678e51bfe9b8c7e1330ad9": "manifest URL refusal",
    # commit message quoting the address its own measurement was made with.
    # Reachable from main and not from the published head, so the address is
    # unpublished and a message rewrite has to reach it before the first push.
    # The exemption records that rather than implying the scan found nothing.
    "231bc1d4677d76a5585f2d033bd638a42d5818c7": "object-database scan measurement",
}
# A blob above this is not prose. The largest text object in this repository
# is under 100 KiB.
MAX_SCANNED_OBJECT = 2 * 1024 * 1024
_EXEMPT_BASENAME = SCAN_EXEMPT[0].rsplit("/", 1)[-1].encode()


def object_records() -> list[tuple[str, str, bytes]] | None:
    """Every object in the database, as (sha, type, body). None without git.

    One `git cat-file --batch --batch-all-objects` call. Records are
    `<sha> <type> <size>\\n<body>\\n`, so the body is taken by length and a
    binary tree survives the split.
    """
    try:
        proc = _subprocess.run(
            ["git", "cat-file", "--batch", "--batch-all-objects"],
            cwd=ROOT,
            capture_output=True,
            timeout=300,
        )
    except OSError, _subprocess.SubprocessError:
        return None
    if proc.returncode != 0:
        return None
    out = proc.stdout
    records: list[tuple[str, str, bytes]] = []
    pos = 0
    while pos < len(out):
        end = out.find(b"\n", pos)
        if end < 0:
            break
        parts = out[pos:end].split()
        if len(parts) != 3:
            break
        sha, kind, size = parts[0].decode(), parts[1].decode(), int(parts[2])
        records.append((sha, kind, out[end + 1 : end + 1 + size]))
        pos = end + 1 + size + 1
    return records


def netblock_blobs(records: list[tuple[str, str, bytes]]) -> set[str]:
    """Every blob SHA recorded under the exempt file name in any tree."""
    shas: set[str] = set()
    for _sha, kind, body in records:
        if kind != "tree":
            continue
        pos = 0
        while pos < len(body):
            sep = body.find(b"\0", pos)
            if sep < 0:
                break
            name = body[pos:sep].split(b" ", 1)[-1]
            if name == _EXEMPT_BASENAME:
                shas.add(body[sep + 1 : sep + 21].hex())
            pos = sep + 21
    return shas


def git_line(*args: str) -> str | None:
    """The first line `git args` prints, stripped. None when git cannot run."""
    try:
        proc = _subprocess.run(
            ["git", *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except OSError, _subprocess.SubprocessError:
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def refuse_truncated_history(records: list[tuple[str, str, bytes]]) -> None:
    """Refuse an object database that holds too little history to scan.

    `actions/checkout` fetches depth 1 by default. That database holds the tip
    commit and no other commit message, so every message below the tip passes
    unread and the run is a clean result computed from objects it never saw.
    The measurement that motivated this guard was read before it existed: a
    `--depth 1` clone scanned 51 objects and exited 0. Measured again at
    54a58db with the guard in place: the `--depth 1` clone scans 51 objects and
    exits 1 here, and a full clone of the same HEAD scans 326 and exits 0.
    """
    check(
        git_line("rev-parse", "--is-shallow-repository") != "true",
        "the object database is shallow, so the scan read the tip commit "
        "message and no other - fetch the full history before running this",
    )
    commits = sum(1 for _sha, kind, _body in records if kind == "commit")
    refs = git_line("for-each-ref", "--format=%(refname)")
    ref_count = len(refs.splitlines()) if refs else 0
    check(
        commits > 1 or ref_count < 2,
        f"the object database holds {commits} commit object across "
        f"{ref_count} refs, so the scan read a truncated history",
    )


def scan_object_database(name_re: Any = None) -> None:
    """Refuse a development host in any object this clone can serve by SHA.

    The SHA of a matching object is withheld under CI. It is a complete
    retrieval key on a public repository - `git cat-file -p` in any clone, and
    the REST blob endpoint with no clone at all - so printing it beside a
    withheld string publishes what the string was withheld for. The number of
    failure lines is the number of matching objects; a maintainer reads the
    SHAs from a local run.

    The unread objects are counted beside the read ones. A count of what was
    scanned reads as coverage on its own, and a binary blob or an oversized one
    leaves the pass silently.
    """
    records = object_records()
    if records is None:
        notes.append("git not available - the object database was not scanned")
        return
    refuse_truncated_history(records)
    exempt = netblock_blobs(records) | set(SCAN_EXEMPT_OBJECTS)
    seen = 0
    binary = 0
    oversized = 0
    for sha, kind, body in records:
        if kind not in ("blob", "commit") or sha in exempt:
            continue
        if len(body) > MAX_SCANNED_OBJECT:
            oversized += 1
            continue
        try:
            text = body.decode("utf-8")
        except UnicodeDecodeError:
            binary += 1
            continue
        seen += 1
        found = tree_hits(text, name_re)
        if found:
            rules_fired = sorted({rule for _n, _h, rule in found})
            rules = ", ".join(rules_fired)
            noun = "rule" if len(rules_fired) == 1 else "rules"
            hosts = ", ".join(sorted({disclose(host) for _n, host, _r in found}))
            failures.append(
                f"{kind} {disclose(sha)} matched the {rules} {noun} on {hosts}"
                " - a forge serves an object by SHA whether or not a ref "
                "reaches it"
            )
    check(seen > 0, "the object-database scan read no objects, so it proved nothing")
    notes.append(
        f"{seen} objects scanned in the object database, {binary} skipped as "
        f"non-text, {oversized} over the {MAX_SCANNED_OBJECT} byte limit"
    )
    notes.append(
        f"{len(exempt)} objects exempt from the object scan by SHA or by file name"
    )


def refuse_unpublished_paths() -> None:
    """Refuse a working-copy-only path that has reached git's index.

    An ignore rule cannot do this job. .gitignore ships, so its rules describe
    the files they hide, and a rule moved to .git/info/exclude protects the one
    machine holding that file and no clone. This check is in the tree, so it
    travels.
    """
    listing = git_line("ls-files", "--cached")
    if listing is None:
        notes.append("git not available - the index was not read for staged notes")
        return
    for path in listing.splitlines():
        if path.startswith(UNPUBLISHED_PATHS) or path in UNPUBLISHED_PATHS:
            failures.append(
                f"{path} is tracked; it is a working-copy path and a clone "
                "must not carry it"
            )


def scan_published_tree(name_re: Any = None, phrases: tuple[str, ...] = ()) -> None:
    """Refuse a development host or infrastructure phrase in the published tree."""
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
    seen = 0
    for path in published_files():
        full = os.path.join(ROOT, *path.split("/"))
        if not os.path.isfile(full):
            continue
        try:
            text = read(full)
        except OSError, UnicodeDecodeError:
            continue
        seen += 1
        for number, host, rule in tree_hits(text, name_re, phrases):
            tail = (
                "that phrase names this network's own infrastructure and "
                "belongs in a maintainer record"
                if rule == RULE_PHRASE
                else "that host is on the development network and means "
                "nothing to a user who installs this"
            )
            failures.append(
                f"{path}:{number} matched the {rule} rule on {disclose(host)} - {tail}"
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
            f"manifest {key} names {disclose(host or '')}, which is not "
            "reachable from outside this network - publish the URL a user can "
            "open",
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
    const_version = constants(const_src, "VERSION").get("VERSION")
    check(
        const_version == manifest.get("version"),
        f"const.VERSION {const_version!r} != manifest version "
        f"{manifest.get('version')!r} - HA reports one and HACS the other",
    )
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
            check(
                False,
                "PyYAML not installed - quality_scale.yaml was not parsed, so its "
                "checks did not run; run under the repo .venv",
            )

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
    # The names come from outside the tree, because naming them in a published
    # file is the disclosure these scans exist to prevent. Both scans get them.
    dev_names = internal_names()
    dev_name_re = name_matcher(dev_names)
    dev_phrases = tuple(internal_phrases())
    for kind, values, env, path in (
        ("development host name", dev_names, DEV_HOST_ENV, DEV_HOST_FILE),
        ("infrastructure phrase", dev_phrases, DEV_PHRASE_ENV, DEV_PHRASE_FILE),
    ):
        if values:
            plural = "" if len(values) == 1 else "s"
            notes.append(f"{len(values)} {kind}{plural} given to the scans")
            continue
        # Under CI this half has no input by design and the note says so. Off
        # CI it is a failure: a maintainer's clean exit has to mean the half
        # ran, and a note is what an absent input looked like while the name
        # half silently covered nothing.
        message = (
            f"no {kind}s given to the scans, so that half did not run; set "
            f"{env}, or write {path}, to run it"
        )
        if redacting():
            notes.append(f"{message}, and read this result as covering the rest")
        else:
            failures.append(message)
    refuse_unpublished_paths()
    scan_controls(dev_names, dev_name_re, dev_phrases)
    scan_published_tree(dev_name_re, dev_phrases)
    scan_object_database(dev_name_re)

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
