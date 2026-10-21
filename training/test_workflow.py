from copy import deepcopy

import pytest

from prepare_data import leaf_identifier, make_split_records
from workflow import CROP_NAMES, DISEASE_NAMES


def records():
    return [
        {"source": f"raw/color/Apple___healthy/id{i}___leaf{i}.jpg",
         "class": "Apple___healthy", "sha256": f"hash{i}"}
        for i in range(12)
    ]


def test_same_leaf_and_duplicate_bytes_cannot_cross_splits():
    samples = records()
    samples[1]["sha256"] = samples[0]["sha256"]
    leaves = {"leaf1": ["shared"], "leaf2": ["shared"]}
    test = {samples[0]["source"]}
    result, moved = make_split_records(samples, leaves, test, 100, 0.25)
    assert moved == 2
    assert {row["split"] for row in result[:3]} == {"test"}
    assert {row["split"] for row in result} == {"train", "val", "test"}
    for field in ("sha256", "leaf_id", "group_id"):
        for value in {row[field] for row in result}:
            assert len({row["split"] for row in result if row[field] == value}) == 1


def test_split_is_reproducible_and_test_is_never_used_as_validation():
    samples = records()
    test = {samples[0]["source"]}
    one, _ = make_split_records(deepcopy(samples), {}, test, 42, 0.25)
    two, _ = make_split_records(deepcopy(samples), {}, test, 42, 0.25)
    assert one == two
    assert one[0]["split"] == "test"


def test_conflicting_duplicate_labels_fail():
    samples = records()
    samples[1]["sha256"] = samples[0]["sha256"]
    samples[1]["class"] = "different"
    with pytest.raises(ValueError, match="Conflicting"):
        make_split_records(samples, {}, set(), 42, 0.25)


def test_insufficient_training_groups_fail_instead_of_leaking():
    with pytest.raises(ValueError, match="No validation"):
        make_split_records(records()[:1], {}, set(), 42, 0.25)


def test_leaf_id_normalizes_mask_and_copy_suffixes():
    path = "raw/color/Apple___healthy/id___ABC copy2_final_masked.JPG"
    assert leaf_identifier(path, {"abc": ["group"]}) == "group"


def test_class_labels_cover_all_source_classes():
    from prepare_data import DATA
    metadata = DATA / "source/splits/color_train.txt"
    names = {line.split("/")[2] for line in metadata.read_text().splitlines()}
    assert len(names) == 38
    for name in names:
        crop, disease = name.split("___", 1)
        assert crop in CROP_NAMES
        assert disease in DISEASE_NAMES
