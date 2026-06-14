"""Config command: enable/disable/get/list default asset plugs.

    fin config enable <asset>    mark an asset to auto-start with `up`
    fin config disable <asset>   stop auto-starting it
    fin config get <asset>       show one asset's status + details
    fin config list              show all asset plugs and their status
"""

from __future__ import annotations

from fincli.app import EXIT_OK, EXIT_USER
from fincli.commands import reserved
from fincli.core.store import is_asset_enabled, set_asset_enabled
from fincli.plugs.base import PlugType
from fincli.plugs.loader import load_all, load_by_name
from fincli.ui.console import console, error, info, success


def _asset_plug(name: str):
    lp = load_by_name(name)
    if lp is None or lp.plug_type != PlugType.ASSET:
        return None
    return lp


@reserved("config", help="Manage default asset plugs: enable|disable|get|list.")
def config(args: list[str]) -> int:
    sub = args[0] if args else "list"
    target = args[1] if len(args) > 1 else None

    if sub == "list":
        return _list()
    if sub in ("enable", "disable", "get"):
        if not target:
            error(f"'config {sub}' requires an asset name.", title="Invalid Argument")
            return EXIT_USER
        if sub == "get":
            return _get(target)
        return _toggle(target, enable=(sub == "enable"))

    error(f"Unknown 'config' subcommand: {sub}.", title="Invalid Argument")
    return EXIT_USER


def _toggle(name: str, *, enable: bool) -> int:
    lp = _asset_plug(name)
    if lp is None:
        error(f"No asset plug named '{name}'.", title="Not Found")
        return EXIT_USER
    set_asset_enabled(lp.instance.name, enable)
    state = "enabled" if enable else "disabled"
    success(f"Asset [bold]{lp.instance.name}[/bold] {state}.")
    return EXIT_OK


def _get(name: str) -> int:
    lp = _asset_plug(name)
    if lp is None:
        error(f"No asset plug named '{name}'.", title="Not Found")
        return EXIT_USER
    plug = lp.instance
    enabled = is_asset_enabled(plug.name)
    info(f"[bold]{plug.name}[/bold] v{plug.version}")
    console.print(f"  status:      {'[green]enabled[/green]' if enabled else '[red]disabled[/red]'}")
    console.print(f"  description: {plug.description or '-'}")
    console.print(f"  commands:    {', '.join(plug.commands().keys()) or '-'}")
    return EXIT_OK


def _list() -> int:
    from rich.table import Table

    assets = [lp for lp in load_all() if lp.plug_type == PlugType.ASSET]
    if not assets:
        info("No asset plugs installed.")
        return EXIT_OK

    table = Table(title="Asset Plugs", header_style="bold cyan", expand=False)
    table.add_column("Asset", style="bold")
    table.add_column("Version", style="magenta")
    table.add_column("Status")
    table.add_column("Description")
    for lp in sorted(assets, key=lambda x: x.instance.name):
        plug = lp.instance
        enabled = is_asset_enabled(plug.name)
        status = "[green]enabled[/green]" if enabled else "[red]disabled[/red]"
        table.add_row(plug.name, plug.version, status, plug.description or "-")
    console.print(table)
    return EXIT_OK
