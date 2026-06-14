"""Tests for fincli.commands.images — ls / rm / prune and image filtering."""

from __future__ import annotations

import pytest

from fincli.app import EXIT_OK, EXIT_USER
from fincli.commands import images as im
from fincli.config import Config

from conftest import make_fake_image


# --------------------------------------------------------------------------- #
# _fin_image_refs / _fin_images filtering
# --------------------------------------------------------------------------- #
def test_fin_image_refs_includes_proxy(monkeypatch, tmp_path):
    import fincli.plugs.loader as loader
    monkeypatch.setattr(loader, "load_all", lambda: [])
    monkeypatch.setattr(im.ProjectEnv, "load",
                        classmethod(lambda cls: im.ProjectEnv(cwd=tmp_path, values={})))
    refs = im._fin_image_refs()
    assert Config.PROXY_IMAGE in refs


def test_fin_images_filters_to_wanted(monkeypatch, patch_docker, tmp_path):
    monkeypatch.setattr(im, "_fin_image_refs", lambda: {"mysql:8.0", Config.PROXY_IMAGE})
    wanted = make_fake_image(tags=["mysql:8.0"])
    other = make_fake_image(tags=["nginx:latest"])
    repo_match = make_fake_image(tags=["mysql:5.7"])  # repo matches "mysql"
    patch_docker.images.list.return_value = [wanted, other, repo_match]
    result = im._fin_images()
    assert wanted in result
    assert repo_match in result
    assert other not in result


# --------------------------------------------------------------------------- #
# images command dispatch
# --------------------------------------------------------------------------- #
def test_images_ls_empty(monkeypatch):
    monkeypatch.setattr(im, "_fin_images", lambda: [])
    assert im.images([]) == EXIT_OK
    assert im.images(["ls"]) == EXIT_OK


def test_images_ls_with_results(monkeypatch):
    monkeypatch.setattr(im, "_fin_images", lambda: [make_fake_image(tags=["demo:1"])])
    monkeypatch.setattr(im, "make_image_table", lambda *a, **k: "TABLE")
    assert im.images(["ls"]) == EXIT_OK


def test_images_rm_requires_arg(monkeypatch, patch_docker):
    assert im.images(["rm"]) == EXIT_USER


def test_images_rm(monkeypatch, patch_docker):
    rc = im.images(["rm", "demo:1"])
    assert rc == EXIT_OK
    patch_docker.images.remove.assert_called_once_with("demo:1", force=False)


def test_images_rm_force(monkeypatch, patch_docker):
    im.images(["rm", "demo:1", "-f"])
    patch_docker.images.remove.assert_called_once_with("demo:1", force=True)


def test_images_prune_none(monkeypatch, patch_docker):
    patch_docker.images.list.return_value = []  # no dangling
    assert im.images(["prune"]) == EXIT_OK
    patch_docker.images.prune.assert_not_called()


def test_images_prune_declined(monkeypatch, patch_docker):
    patch_docker.images.list.return_value = [make_fake_image()]
    monkeypatch.setattr(im, "confirm", lambda *a, **k: False)
    assert im.images(["prune"]) == EXIT_OK
    patch_docker.images.prune.assert_not_called()


def test_images_prune_confirmed(monkeypatch, patch_docker):
    patch_docker.images.list.return_value = [make_fake_image()]
    patch_docker.images.prune.return_value = {"SpaceReclaimed": 2 * 1_048_576}
    monkeypatch.setattr(im, "confirm", lambda *a, **k: True)
    assert im.images(["prune"]) == EXIT_OK
    patch_docker.images.prune.assert_called_once()


def test_images_unknown_subcommand(monkeypatch, patch_docker):
    assert im.images(["bogus"]) == EXIT_USER
