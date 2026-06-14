"""Image commands: ``fin images ls|rm|prune`` (alias ``img``).

Lists only Fin-related images — those used by loaded plugs plus the proxy —
so the output stays focused on what Fin manages rather than the whole host.
"""

from __future__ import annotations

from fincli.app import EXIT_OK, EXIT_USER
from fincli.commands import reserved
from fincli.config import Config
from fincli.core.docker_client import get_docker
from fincli.core.env import ProjectEnv
from fincli.ui.console import confirm, console, error, info, success, warning
from fincli.ui.tables import make_image_table


def _fin_image_refs() -> set[str]:
    """Collect image references Fin cares about: proxy + every plug spec."""
    refs: set[str] = {Config.PROXY_IMAGE}
    from fincli.plugs.loader import load_all

    env = ProjectEnv.load()
    for lp in load_all():
        plug = lp.instance
        try:
            spec = plug.primary_spec(env)
            if spec:
                refs.add(spec.image)
            for aspec in plug.asset_specs(env):
                refs.add(aspec.image)
        except Exception:  # noqa: BLE001 - never let one plug break the list
            continue
    return refs


def _fin_images() -> list:
    client = get_docker().client
    wanted = _fin_image_refs()
    wanted_repos = {r.split(":")[0] for r in wanted}
    result = []
    for img in client.images.list():
        tags = img.tags or []
        if any(t in wanted or t.split(":")[0] in wanted_repos for t in tags):
            result.append(img)
    return result


@reserved("images", help="Manage Fin images: ls | rm <image> | prune.", aliases=("img",), group="Images")
def images(args: list[str]) -> int:
    sub = args[0] if args else "ls"
    rest = args[1:]

    if sub in ("ls", "list"):
        imgs = _fin_images()
        if not imgs:
            info("No Fin-related images found.")
            return EXIT_OK
        console.print(make_image_table(imgs, title="Fin Images"))
        return EXIT_OK

    if sub == "rm":
        if not rest:
            error("Usage: fin images rm <image>", title="Invalid Argument")
            return EXIT_USER
        client = get_docker().client
        client.images.remove(rest[0], force="-f" in rest or "--force" in rest)
        success(f"Removed image [bold]{rest[0]}[/bold]")
        return EXIT_OK

    if sub == "prune":
        client = get_docker().client
        dangling = client.images.list(filters={"dangling": True})
        if not dangling:
            info("No dangling images to prune.")
            return EXIT_OK
        if not confirm(f"Remove {len(dangling)} dangling image(s)?", default=False):
            info("Aborted.")
            return EXIT_OK
        pruned = client.images.prune(filters={"dangling": True})
        reclaimed = pruned.get("SpaceReclaimed", 0)
        success(f"Pruned dangling images, reclaimed {reclaimed / 1_048_576:.1f} MB")
        return EXIT_OK

    error(f"Unknown 'images' subcommand: {sub}. Use ls | rm | prune.", title="Invalid Argument")
    return EXIT_USER
