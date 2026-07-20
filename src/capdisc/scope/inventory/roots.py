"""Root/path discovery: the real `.claude`/managed directories to scan for each scope."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import get_args

from ...base import FrozenModel
from ..locations import Artifact
from ..types import ArtifactKind, ScanBasePath, ScopeKind


def artifact_kinds() -> list[Artifact]:
    """One canonical instance of every artifact descriptor, derived from the union, not listed."""
    return [variant() for variant in get_args(get_args(Artifact)[0])]


def _project_bases(start: Path) -> list[Path]:
    """The project-scope `.claude` directories, walking up from `start` to the repo root.

    How Claude Code finds project scope no matter which subdirectory you launched from.

    Args:
        start: The directory the search walks up from (resolved first).

    Returns:
        Each `.claude` from `start` up to and including the repo root, nearest first. With no
        enclosing repo, just the start dir's own `.claude`, or `[]` if it has none.
    """
    start = start.resolve()
    bases: list[Path] = []
    for current in (start, *start.parents):
        claude_dir = current / ".claude"
        if claude_dir.is_dir():
            bases.append(claude_dir)
        if (current / ".git").exists():
            return bases
    start_claude = start / ".claude"
    return [start_claude] if start_claude.is_dir() else []


# Directories never worth descending into when looking for nested skills.
_IGNORED_DIRS = frozenset({".git", ".venv", "venv", "node_modules", "__pycache__", ".tox"})
_STANDALONE_KINDS = frozenset({ArtifactKind.agent, ArtifactKind.skill, ArtifactKind.command})


def _nested_skill_bases(start: Path) -> list[Path]:
    """The `.claude` directories below `start`, for skills.

    Skills (unlike agents) also load from nested `.claude/skills/` in subdirectories.

    Args:
        start: The directory to search beneath (resolved first).

    Returns:
        Every `.claude` strictly below `start`, sorted; the start's own `.claude` is excluded (it
        is already an upward base) and noise dirs (`.git`, `node_modules`, …) are pruned.
    """
    start = start.resolve()
    own = start / ".claude"
    bases: list[Path] = []
    for root, dirnames, _files in os.walk(start):
        # prune in place so os.walk never descends into a noise tree at all — unlike rglob,
        # which would first walk the whole subtree and only filter its matches afterward
        dirnames[:] = [d for d in dirnames if d not in _IGNORED_DIRS]
        if ".claude" in dirnames:
            candidate = Path(root) / ".claude"
            if candidate != own:
                bases.append(candidate)
    return sorted(bases)


_MANAGED_DIRS: dict[str, Path] = {
    "darwin": Path("/Library/Application Support/ClaudeCode"),
    "linux": Path("/etc/claude-code"),
    "win32": Path(r"C:\Program Files\ClaudeCode"),
}


def default_managed_dir() -> Path | None:
    """The OS file-based managed-settings directory for this platform.

    Only the file delivery mechanism is a path; MDM, registry, and server-delivered managed
    settings are not files and cannot be scanned here.

    Returns:
        The platform's managed dir, or None on an unrecognised platform.
    """
    for prefix, path in _MANAGED_DIRS.items():
        if sys.platform.startswith(prefix):
            return path
    return None


class ScanRoot(FrozenModel):
    """A real base directory to scan for a scope. `kinds` restricts which artifact kinds use it
    (None = all): a nested-skill root serves only skills, a managed `.claude` only standalone
    files, while the managed root itself serves the settings file."""

    scope: ScopeKind
    base: ScanBasePath
    kinds: frozenset[ArtifactKind] | None = None


class ScopeRoots(FrozenModel):
    """The base directories to scan, in precedence order (highest first). Build with `discover`
    so project scope is resolved by walking up to the repo root, not assumed to be the cwd."""

    roots: list[ScanRoot] = []

    @classmethod
    def discover(
        cls,
        *,
        start: Path,
        home_dir: Path | None = None,
        managed_dir: Path | None = None,
        plugin_dirs: list[Path] | None = None,
        add_dirs: list[Path] | None = None,
    ) -> ScopeRoots:
        """Resolve every scannable root from where Claude Code was started.

        - project: every `.claude` from `start` up to the repo root (all kinds), plus every
          `.claude` *below* `start` for skills, plus each `--add-dir`'s `.claude`.
        - user / managed: included only when their dir is given — `discover` never auto-resolves
          them. Managed splits: the dir itself holds `managed-settings.json`; its `.claude` holds
          standalone files.
        - plugin: the explicit `plugin_dirs` only.

        Args:
            start: The launch directory; project scope is resolved by walking up from here.
            home_dir: The user's home; when given, its `.claude` is the user-scope root.
            managed_dir: The OS managed dir; when given, it and its `.claude` are added (use
                `default_managed_dir()` to obtain it).
            plugin_dirs: Installed-plugin roots to scan; enabled-plugin resolution is the
                caller's job, since plugins resolve through `enabledPlugins` + marketplaces.
            add_dirs: Extra `--add-dir` roots; each contributes its `.claude` as project scope.

        Returns:
            The scan roots in precedence order, highest first.
        """
        plugin_dirs = plugin_dirs or []
        add_dirs = add_dirs or []
        roots: list[ScanRoot] = []
        if managed_dir is not None:
            roots.append(ScanRoot(scope=ScopeKind.managed, base=managed_dir))
            roots.append(
                ScanRoot(
                    scope=ScopeKind.managed,
                    base=managed_dir / ".claude",
                    kinds=_STANDALONE_KINDS,
                )
            )
        # Launched from the home directory itself (cwd = ~), the walk-up finds `~/.claude`
        # and would label it project scope while the same physical directory is also added
        # as the user root below — double-capturing every artifact it holds. The user root
        # is the true owner; drop the project-scope alias.
        user_claude = (home_dir / ".claude").resolve() if home_dir is not None else None
        roots += [
            ScanRoot(scope=ScopeKind.project, base=base)
            for base in _project_bases(start)
            if base.resolve() != user_claude
        ]
        roots += [
            ScanRoot(scope=ScopeKind.project, base=base, kinds=frozenset({ArtifactKind.skill}))
            for base in _nested_skill_bases(start)
        ]
        # resolved, like _project_bases/_nested_skill_bases: an unresolved add-dir that's a
        # symlink to (or through) `start` or another add-dir would otherwise scan the same
        # physical directory twice, double-capturing every additive artifact it holds.
        seen_project_bases = {
            root.base.resolve() for root in roots if root.scope == ScopeKind.project
        }
        if user_claude is not None:
            seen_project_bases.add(user_claude)
        for add in add_dirs:
            claude_dir = (add / ".claude").resolve()
            if claude_dir.is_dir() and claude_dir not in seen_project_bases:
                seen_project_bases.add(claude_dir)
                roots.append(ScanRoot(scope=ScopeKind.project, base=claude_dir))
        if home_dir is not None:
            roots.append(ScanRoot(scope=ScopeKind.user, base=home_dir / ".claude"))
        roots += [ScanRoot(scope=ScopeKind.plugin, base=plugin) for plugin in plugin_dirs]
        return cls(roots=roots)
