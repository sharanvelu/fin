"""Fin plugin system — the core extensibility layer.

A *plug* is a Python package that defines one subclass of
:class:`fincli.plugs.base.FinPlug`. Plugs come in three types:

* ``APP``    — a runnable application (Laravel, Django, …). Provides the
  primary container spec and app-specific commands.
* ``ASSET``  — a shared auxiliary service (MySQL, Redis, Postgres, …).
* ``GLOBAL`` — commands available everywhere, not tied to a project.
"""
