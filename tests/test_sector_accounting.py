"""Turn 1b.3: every byte of every file is classified -- nothing is silently absorbed.

``cfb.classify_sectors`` gives every sector-sized window exactly one of the eight classes
``header, difat, fat, minifat, directory, stream, free, slack`` (in that fixed order) and
reports, separately, the bytes no class claims (``unaccounted``). The eight classes plus
``unaccounted`` sum to the file length on **any** input; on a well-formed file
``unaccounted`` is 0. ``free`` is a window the FAT marks ``FREESECT`` and no chain reaches;
``slack`` is a partial tail window no chain reaches. A cyclic chain puts its unreachable
sectors in ``unaccounted`` -- never into another class.

The three declared tests are ``test_the_eight_classes_sum_to_the_file_length``,
``test_free_and_slack_are_explicit`` and ``test_a_cyclic_chain_is_visible_as_unaccounted``.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

import make_msg_fixtures  # noqa: E402

from emailextract import cfb  # noqa: E402
from support import cfb_raw, msg_construction  # noqa: E402

CONSTRUCTION = msg_construction.CONSTRUCTION
HOSTILE = msg_construction.HOSTILE_EXPECTATIONS


def _fixture(name: str) -> bytes:
    return make_msg_fixtures.build_fixture(name)


def _total(accounting, unaccounted: int) -> int:
    return sum(bytes_ for _, bytes_ in accounting) + unaccounted


def test_the_eight_classes_sum_to_the_file_length() -> None:
    for name in make_msg_fixtures.FIXTURE_NAMES:
        data = _fixture(name)
        opened = cfb.open_cfb(data, require_properties=False)
        assert isinstance(opened, cfb.CfbFile), name
        assert [label for label, _ in opened.accounting] == list(cfb.SECTOR_CLASSES), name
        assert opened.unaccounted == 0, name
        assert _total(opened.accounting, opened.unaccounted) == len(data), name
        expected = [tuple(row) for row in CONSTRUCTION[name]["sector_accounting"]]
        assert [tuple(row) for row in opened.accounting] == expected, name


def test_free_and_slack_are_explicit() -> None:
    assert "unaccounted" not in cfb.SECTOR_CLASSES

    # A whole window the FAT marks FREESECT and no chain reaches is ``free``, not dropped:
    # the mini stream is the root's 2-sector chain (3, 4); cut it to one and mark both FAT
    # slots FREESECT, so sector 4 is unclaimed and its own FAT slot says it is free.
    data = _fixture("msg_headers_only")
    fields = cfb_raw.header(data)
    fat_base = (fields["difat"][0] + 1) * fields["sector_size"]
    freed = data
    for slot in (3, 4):
        freed = cfb_raw.patch_u32(freed, fat_base + 4 * slot, cfb_raw.FREESECT)
    opened = cfb.open_cfb(freed, require_properties=False)
    assert isinstance(opened, cfb.CfbFile)
    classes = opened.accounting_map()
    assert classes["free"] == fields["sector_size"] == 512
    assert opened.unaccounted == 0
    assert _total(opened.accounting, opened.unaccounted) == len(freed)

    # A partial tail window no chain reaches is ``slack``; the sum still closes.
    extended = data + b"\x00" * 100
    opened = cfb.open_cfb(extended, require_properties=False)
    classes = opened.accounting_map()
    assert classes["slack"] == 100
    assert classes["free"] == 0
    assert opened.unaccounted == 0
    assert _total(opened.accounting, opened.unaccounted) == len(extended) == len(data) + 100


def test_a_cyclic_chain_is_visible_as_unaccounted() -> None:
    data = _fixture("msg_fat_cycle")
    expected = HOSTILE["msg_fat_cycle"]
    opened = cfb.open_cfb(data)
    assert isinstance(opened, cfb.CfbFile)
    # The sectors the cycle put out of reach are their own count, never folded into a class.
    assert opened.unaccounted == expected["unaccounted"] > 0
    assert opened.accounting_map()["free"] == 0
    assert _total(opened.accounting, opened.unaccounted) == len(data)

    # The same count appears on a file the cycle shortens: the tail sector is out of reach.
    short = cfb.open_cfb(data[: 12 * 512], require_properties=False)
    assert short.unaccounted > 0
    assert _total(short.accounting, short.unaccounted) == len(data[: 12 * 512])
