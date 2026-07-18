# capdisc

[![PyPI](https://img.shields.io/pypi/v/claude-code-capabilities.svg)](https://pypi.org/project/claude-code-capabilities/)
[![Python versions](https://img.shields.io/pypi/pyversions/claude-code-capabilities.svg)](https://pypi.org/project/claude-code-capabilities/)
[![CI](https://github.com/Magic-Man-us/capability-discovery/actions/workflows/ci.yml/badge.svg)](https://github.com/Magic-Man-us/capability-discovery/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/Magic-Man-us/capability-discovery/graph/badge.svg)](https://codecov.io/gh/Magic-Man-us/capability-discovery)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/Magic-Man-us/capability-discovery/blob/main/LICENSE)

Discovers Claude Code capabilities — skills, agents, plugins, MCP servers, hooks — into typed
Pydantic catalogs and an environment report.

## Install

```bash
uv add claude-code-capabilities
# or
pip install claude-code-capabilities
```

## CLI

```bash
capdisc            # scan this machine, write discovery-report.json + .html
capdisc --oauth     # also allow the interactive OAuth flow for HTTP MCP servers
                    # with a pre-registered client (forces a fresh MCP harvest)
```

Both files are written to `~/.claude/capdisc/` by default. Configure paths and MCP auth via env
vars (`CAPDISC_` prefix), a `.env` file, or `~/.claude/capdisc/config.json`/`config.yaml` — see
`DiscoverySettings` in `settings.py` for every field.

## Library

Scan the machine into a typed catalog:

```python
from pathlib import Path
from capdisc.discovery import scan_environment
from capdisc.scope import ScopeRoots

roots = ScopeRoots.discover(start=Path.cwd(), home_dir=Path.home())
catalog = scan_environment(roots)
for entry in catalog.entries:
    ...  # CatalogSkill | CatalogTool | CatalogMcpServer | CatalogPlugin
```

Build and persist the full environment report (what the CLI does):

```python
from capdisc.report import build_report, write_report

report = build_report(oauth=False)
write_report(report)  # -> ~/.claude/capdisc/discovery-report.{json,html}
```

Inspect the on-disk scope inventory directly — every skill/agent/command/hook found, its
precedence, and which ones actually win a collision:

```python
from capdisc.scope import ScopeInventory, ScopeRoots

inventory = ScopeInventory.scan(ScopeRoots.discover(start=Path.cwd(), home_dir=Path.home()))
print(len(inventory.artifacts), "captured,", len(inventory.effective), "in effect")
for hooks in inventory.hook_configs:
    ...  # HookConfig, unified from settings.json and component frontmatter
```

### MCP servers

Read the last harvested tool inventory (fast, no network — served from a 12h cache):

```python
from capdisc.mcp_harvest import read_mcp_cache, cache_is_stale

servers = read_mcp_cache()  # [] if there's no cache yet
if cache_is_stale():
    ...  # trigger a refresh (below) before trusting this
```

Force a fresh harvest — connects to every configured server concurrently (bounded) and lists
their real tool schemas:

```python
from capdisc.mcp_harvest import refresh_mcp_cache

servers = refresh_mcp_cache(oauth=False)  # also (re)writes the cache
for server in servers:
    print(server.ref, [t.name for t in server.tools])
```

Bearer/OAuth auth for HTTP servers is opt-in via settings, bound to an exact hostname so a
same-named server elsewhere can never receive a credential meant for another:

```bash
export CAPDISC_MCP_BEARER_ENV='{"github": {"env": "GH_TOKEN", "host": "api.githubcopilot.com"}}'
```

`report.EnvironmentReport` captures the full discovery harvest (scan roots, on-disk inventory, skills,
builtin tools, plugins with per-component token cost, MCP servers). `mcp_harvest` and `mcp_catalog`
enumerate connected MCP servers; `plugin_catalog` reads installed plugins; `scope` resolves which
roots to scan.

The package ships `py.typed`.

## Tests

```bash
uv run pytest
uv run mypy src
uv run ruff check .
```
