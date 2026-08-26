"""Concurrent image prefetching for ``fin up``.

``containers.run`` transparently pulls a missing image, but only when that
container starts — so a first ``fin up`` with several plugs downloads every
image sequentially. Pre-pulling all missing images concurrently up front turns
that wall-clock cost from the *sum* of the downloads into roughly the slowest
single one. Images already present locally are never touched, and the SDK's
implicit pull remains as a fallback for anything not prefetched.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Iterable

from fincli.core.docker_client import get_docker
from fincli.core.errors import FinError
from fincli.ui.console import success
from fincli.ui.spinners import live_checklist

#: Upper bound on concurrent pulls. The daemon already parallelises layer
#: downloads within each pull, so more workers stop paying off quickly.
MAX_CONCURRENT_PULLS = 4


def missing_images(images: Iterable[str]) -> list[str]:
    """Return the unique image refs from *images* not present locally.

    Order is preserved; empty entries and duplicates are dropped. A ref that
    cannot be inspected counts as missing — worst case it gets pulled (or the
    pull surfaces the real error).
    """
    client = get_docker().client
    missing: list[str] = []
    for ref in dict.fromkeys(i for i in images if i):
        try:
            client.images.get(ref)
        except Exception:  # noqa: BLE001 - absent or unreadable → pull it
            missing.append(ref)
    return missing


def prefetch_images(images: Iterable[str]) -> None:
    """Concurrently pull any of *images* not already available locally.

    A no-op (with no output) when everything is present. All pulls run to
    completion even if one fails; failures are then raised together as a
    single :class:`FinError` so the user sees every broken ref at once.
    """
    missing = missing_images(images)
    if not missing:
        return

    client = get_docker().client
    failures: dict[str, str] = {}
    with live_checklist("Pulling images", missing) as set_line:
        with ThreadPoolExecutor(
            max_workers=min(MAX_CONCURRENT_PULLS, len(missing))
        ) as pool:
            futures = {pool.submit(client.images.pull, ref): ref for ref in missing}
            for future in as_completed(futures):
                ref = futures[future]
                try:
                    future.result()
                except Exception as exc:  # noqa: BLE001 - normalised below
                    message = str(getattr(exc, "explanation", None) or exc)
                    failures[ref] = message
                    set_line(ref, f"[red]✗[/red] {ref} [dim]— {message}[/dim]")
                else:
                    set_line(ref, f"[green]✓[/green] {ref}")

    if failures:
        plural = "s" if len(failures) > 1 else ""
        listing = "\n".join(f"  {ref}: {msg}" for ref, msg in failures.items())
        raise FinError(
            f"Could not pull {len(failures)} image{plural}:\n{listing}\n"
            "Check the image name/tag and your network or registry access, "
            "then run 'fin up' again.",
            title="Image Pull Failed",
        )
    plural = "s" if len(missing) > 1 else ""
    success(f"Pulled {len(missing)} image{plural}.")
