"""Plugin loader — discovers and instantiates plugs via importlib.

Discovery model — one shape, a flat directory of single-file plugs:

    PLUGS_DIR/
      <plug_name>.py      → defines exactly one FinPlug subclass

For development, symlink the fin-plugs repo's ``plugs/`` directory to
``PLUGS_DIR`` (``ln -s <fin-plugs repo>/plugs ~/.fin/plugs``); installed
plugs land in the same directory. The loader imports each file, finds the
single class extending :class:`FinPlug`, instantiates it, calls ``setup()``,
and returns it. The plug's type is its declared ``plug_type``. Load failures
are reported as warnings — one bad plug never crashes Fin.
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


def _import_file(py: Path):
    """Import a single-file plug and return the module object."""
    mod_name = f"fin_plug_{py.parent.name}_{py.stem}"
    spec = importlib.util.spec_from_file_location(mod_name, py)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot build import spec for {py}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


def load_plug_file(py: Path) -> LoadedPlug | None:
    """Load a single-file plug (``<name>.py``). Returns None on failure."""
    try:
        module = _import_file(py)
    except Exception as exc:  # noqa: BLE001 - we degrade gracefully
        warning(f"Failed to import plug at {py.name}: {exc}")
        return None

    plug_cls = _find_plug_class(module)
    if plug_cls is None:
        warning(f"No FinPlug subclass found in plug '{py.stem}' — skipping.")
        return None

    try:
        instance = plug_cls()
        instance.setup()
    except Exception as exc:  # noqa: BLE001
        warning(f"Failed to initialise plug '{py.stem}': {exc}")
        return None

    return LoadedPlug(instance=instance, path=py, plug_type=instance.plug_type)


def _iter_plug_files(base: Path) -> Iterable[Path]:
    """Yield the ``<name>.py`` plug candidates directly under *base*."""
    if not base.is_dir():
        return
    for child in sorted(base.iterdir()):
        if child.name.startswith((".", "_")):
            continue
        if child.is_file() and child.suffix == ".py":
            yield child


def load_all(plugs_dir: Path | None = None) -> list[LoadedPlug]:
    """Discover and load every ``<name>.py`` plug in the plugs directory."""
    base = plugs_dir or Config.PLUGS_DIR
    loaded: list[LoadedPlug] = []
    for py in _iter_plug_files(base):
        lp = load_plug_file(py)
        if lp is not None:
            loaded.append(lp)
    return loaded


def load_by_name(name: str, plugs_dir: Path | None = None) -> LoadedPlug | None:
    """Load a single plug by name.

    Matches the filename first (``<name>.py``), then falls back to a full
    scan matching each plug's declared ``.name`` attribute.
    """
    base = plugs_dir or Config.PLUGS_DIR
    candidate = base / f"{name}.py"
    if candidate.is_file():
        return load_plug_file(candidate)
    for lp in load_all(base):
        if lp.instance.name == name:
            return lp
    return None
