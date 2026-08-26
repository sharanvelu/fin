"""Tests for fincli.core.images — concurrent image prefetching."""

from __future__ import annotations

import pytest

from fincli.core.errors import FinError
from fincli.core.images import missing_images, prefetch_images


def _local_images(client, present: set[str]) -> None:
    """Make ``client.images.get`` succeed only for *present* refs."""

    def get(ref):
        if ref not in present:
            raise Exception(f"No such image: {ref}")
        return object()

    client.images.get.side_effect = get


# --------------------------------------------------------------------------- #
# missing_images
# --------------------------------------------------------------------------- #
def test_missing_images_filters_present(patch_docker):
    _local_images(patch_docker, present={"redis:7"})
    assert missing_images(["redis:7", "mysql:8.4"]) == ["mysql:8.4"]


def test_missing_images_dedupes_and_keeps_order(patch_docker):
    _local_images(patch_docker, present=set())
    refs = ["mysql:8.4", "redis:7", "mysql:8.4", "", "redis:7"]
    assert missing_images(refs) == ["mysql:8.4", "redis:7"]


# --------------------------------------------------------------------------- #
# prefetch_images
# --------------------------------------------------------------------------- #
def test_prefetch_noop_when_all_present(patch_docker):
    _local_images(patch_docker, present={"redis:7", "mysql:8.4"})
    prefetch_images(["redis:7", "mysql:8.4"])
    patch_docker.images.pull.assert_not_called()


def test_prefetch_pulls_only_missing(patch_docker):
    _local_images(patch_docker, present={"redis:7"})
    prefetch_images(["redis:7", "mysql:8.4", "minio/minio:latest"])
    pulled = {call.args[0] for call in patch_docker.images.pull.call_args_list}
    assert pulled == {"mysql:8.4", "minio/minio:latest"}


def test_prefetch_pulls_each_ref_once(patch_docker):
    _local_images(patch_docker, present=set())
    prefetch_images(["mysql:8.4", "mysql:8.4", "mysql:8.4"])
    assert patch_docker.images.pull.call_count == 1


def test_prefetch_failure_raises_with_all_failed_refs(patch_docker):
    _local_images(patch_docker, present=set())

    def pull(ref):
        if ref != "redis:7":
            raise Exception("manifest unknown")
        return object()

    patch_docker.images.pull.side_effect = pull
    with pytest.raises(FinError) as exc:
        prefetch_images(["redis:7", "mysql:9999", "nope:tag"])
    assert exc.value.title == "Image Pull Failed"
    assert "mysql:9999" in exc.value.message
    assert "nope:tag" in exc.value.message
    # The pull that succeeded is not reported as failed.
    assert "redis:7:" not in exc.value.message


def test_prefetch_failure_still_attempts_every_pull(patch_docker):
    """One broken ref must not stop the other downloads."""
    _local_images(patch_docker, present=set())
    patch_docker.images.pull.side_effect = [Exception("boom"), object(), object()]
    with pytest.raises(FinError):
        prefetch_images(["a:1", "b:2", "c:3"])
    assert patch_docker.images.pull.call_count == 3
