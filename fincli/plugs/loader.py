"""Plugin loader — discovers and instantiates plugs via importlib.

Discovery model (directory grouping):

    PLUGS_DIR/
      App/<plug_name>/__init__.py     → defines a FinPlug subclass
      Asset/<plug_name>/...
      Global/<plug_name>/...

Each plug is a package directory. The loader imports it, finds the single
class extending :class:`FinPlug`, instantiates it, calls ``setup()``, and
returns it. Load failures are reported as warnings — one bad plug never
crashes Fin.
"""

from __future__ import annotations

import importlib.util
import inspect
import sys
from pathlib import Path
from typing import Iterable

from fincli.config import Config
from fincli.plugs.base import FinPlug, PlugType
from fincli.ui.console import warning


class LoadedPlug:
    """A successfully-loaded plug plus where it came from."""

    def __init__(self, instance: FinPlug, path: Path, plug_type: PlugType):
        self.instance = instance
        self.path = path
        self.plug_type = plug_type

    @property
    def name(self) -> str:
        return self.instance.name


def _find_plug_class(module) -> type[FinPlug] | None:
    """Return the FinPlug subclass defined in *module*, if any."""
    for _, obj in inspect.getmembers(module, inspect.isclass):
        if issubclass(obj, FinPlug) and obj is not FinPlug:
            # Only count classes actually defined in this module (not imports).
            if obj.__module__ == module.__name__:
                return obj
    return None


def _import_package(pkg_dir: Path):
    """Import a plug package directory and return the module object."""
    init = pkg_dir / "__init__.py"
    target = init if init.exists() else pkg_dir
    mod_name = f"fin_plug_{pkg_dir.parent.name}_{pkg_dir.name}"

    if init.exists():
        spec = importlib.util.spec_from_file_location(
            mod_name, init, submodule_search_locations=[str(pkg_dir)]
        )
    else:
        # Single-file plug: <name>.py
        py = pkg_dir.with_suffix(".py")
        spec = importlib.util.spec_from_file_location(mod_name, py)
        target = py

    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot build import spec for {target}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


def load_plug_dir(pkg_dir: Path, plug_type: PlugType) -> LoadedPlug | None:
    """Load a single plug package directory. Returns None on failure."""
    try:
        module = _import_package(pkg_dir)
    except Exception as exc:  # noqa: BLE001 - we degrade gracefully
        warning(f"Failed to import plug at {pkg_dir.name}: {exc}")
        return None

    plug_cls = _find_plug_class(module)
    if plug_cls is None:
        warning(f"No FinPlug subclass found in plug '{pkg_dir.name}' — skipping.")
        return None

    try:
        instance = plug_cls()
        instance.setup()
    except Exception as exc:  # noqa: BLE001
        warning(f"Failed to initialise plug '{pkg_dir.name}': {exc}")
        return None

    return LoadedPlug(instance=instance, path=pkg_dir, plug_type=plug_type)


def _iter_plug_dirs(type_dir: Path) -> Iterable[Path]:
    """Yield candidate plug package dirs under a type directory."""
    if not type_dir.is_dir():
        return
    for child in sorted(type_dir.iterdir()):
        if child.name.startswith((".", "_")):
            continue
        if child.is_dir():
            yield child
        elif child.suffix == ".py":
            yield child.with_suffix("")  # treated as single-file plug


def load_all(plugs_dir: Path | None = None) -> list[LoadedPlug]:
    """Discover and load every plug under all type directories."""
    base = plugs_dir or Config.PLUGS_DIR
    loaded: list[LoadedPlug] = []
    for type_name, sub in Config.PLUG_TYPE_DIRS.items():
        type_dir = base / sub
        for pkg_dir in _iter_plug_dirs(type_dir):
            lp = load_plug_dir(pkg_dir, PlugType(type_name))
            if lp is not None:
                loaded.append(lp)
    return loaded


def load_by_name(name: str, plugs_dir: Path | None = None) -> LoadedPlug | None:
    """Load a single plug by name, searching all type directories.

    Returns the first match (App → Asset → Global order).
    """
    base = plugs_dir or Config.PLUGS_DIR
    for type_name, sub in Config.PLUG_TYPE_DIRS.items():
        type_dir = base / sub
        for pkg_dir in _iter_plug_dirs(type_dir):
            if pkg_dir.name == name:
                return load_plug_dir(pkg_dir, PlugType(type_name))
    # Fall back to a full scan matching the plug's declared .name attribute.
    for lp in load_all(base):
        if lp.instance.name == name:
            return lp
    return None
