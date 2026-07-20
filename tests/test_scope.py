from __future__ import annotations

from pathlib import Path

from capdisc.scope import ArtifactKind, ScopeInventory, ScopeKind, ScopeRoots
from helpers import standalone_set, touch


def _effective_scope(inv: ScopeInventory, kind: ArtifactKind, name: str) -> ScopeKind:
    [entry] = [c for c in inv.effective if c.kind is kind and c.name == name]
    return entry.scope


def test_precedence_flips_by_kind(tmp_path: Path) -> None:
    # 'foo' of each kind in both project and user scope; the winner differs by kind.
    repo, home = tmp_path / "repo", tmp_path / "home"
    (repo / ".git").mkdir(parents=True)
    standalone_set(repo / ".claude")
    standalone_set(home / ".claude")
    inv = ScopeInventory.scan(ScopeRoots.discover(start=repo, home_dir=home))

    assert _effective_scope(inv, ArtifactKind.skill, "foo") is ScopeKind.user
    assert _effective_scope(inv, ArtifactKind.command, "foo") is ScopeKind.user
    assert _effective_scope(inv, ArtifactKind.agent, "foo") is ScopeKind.project  # subagents invert


def test_home_launch_does_not_double_scan_user_claude(tmp_path: Path) -> None:
    # Launched from the home directory itself (cwd = ~): `~/.claude` is the user root and
    # must not also be captured as project scope, or every artifact in it lists twice.
    home = tmp_path / "home"
    standalone_set(home / ".claude")
    roots = ScopeRoots.discover(start=home, home_dir=home)

    target = (home / ".claude").resolve()
    labelled = [(root.scope, Path(root.base).resolve()) for root in roots.roots]
    assert (ScopeKind.user, target) in labelled
    assert (ScopeKind.project, target) not in labelled

    inv = ScopeInventory.scan(roots)
    commands = [c for c in inv.artifacts if c.kind is ArtifactKind.command and c.name == "foo"]
    assert len(commands) == 1
    assert commands[0].scope is ScopeKind.user


def test_command_has_no_managed_scope(tmp_path: Path) -> None:
    repo, managed = tmp_path / "repo", tmp_path / "managed"
    (repo / ".git").mkdir(parents=True)
    touch(repo / ".claude" / "commands" / "foo.md")
    touch(managed / "commands" / "bar.md")  # a command in a managed dir must be ignored
    inv = ScopeInventory.scan(ScopeRoots.discover(start=repo, managed_dir=managed))

    commands = [c for c in inv.artifacts if c.kind is ArtifactKind.command]
    assert ScopeKind.managed not in {c.scope for c in commands}
    assert "bar" not in {c.name for c in commands}


def test_nested_project_nearest_wins(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    touch(repo / ".claude" / "agents" / "foo.md", "far")
    deep = repo / "pkg" / "web"
    touch(deep / ".claude" / "agents" / "foo.md", "near")
    inv = ScopeInventory.scan(ScopeRoots.discover(start=deep))

    [entry] = [c for c in inv.effective if c.kind is ArtifactKind.agent and c.name == "foo"]
    assert entry.contents == "near"


def test_project_hooks_capture_both_settings_files(tmp_path: Path) -> None:
    # Regression: a scope can hold multiple locations (committed settings.json AND gitignored
    # settings.local.json). Both hook entries must be captured — not collapsed to one per scope.
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / ".claude").mkdir()
    (repo / ".claude" / "settings.json").write_text('{"hooks": {"PreToolUse": []}}')
    (repo / ".claude" / "settings.local.json").write_text('{"hooks": {"Stop": []}}')
    inv = ScopeInventory.scan(ScopeRoots.discover(start=repo))

    project_hooks = [
        c for c in inv.artifacts if c.kind is ArtifactKind.hook and c.scope is ScopeKind.project
    ]
    assert sorted(c.path.name for c in project_hooks) == ["settings.json", "settings.local.json"]
    # hooks are additive, so both survive resolution
    effective_hooks = [
        c for c in inv.effective if c.kind is ArtifactKind.hook and c.scope is ScopeKind.project
    ]
    assert sorted(c.path.name for c in effective_hooks) == ["settings.json", "settings.local.json"]
