import pytest

from labmate.memory import store
from labmate.memory.sop_handbook import search_sop_handbook


@pytest.fixture(autouse=True)
def isolated_memory_db(tmp_path, monkeypatch):
    """Every test gets its own SQLite file so past test runs (and other
    tests in the same session) can't leak into these assertions.
    """
    monkeypatch.setattr(store, "VAR_DIR", tmp_path)


def test_qa_round_trip():
    store.record_qa("literature", "what's new on lipid nanoparticles?", "here's a summary...")
    result = store.search_past_qa("lipid nanoparticles")
    assert len(result["results"]) == 1
    assert result["results"][0]["specialist"] == "literature"


def test_qa_search_no_match_is_explicit():
    result = store.search_past_qa("something never asked about")
    assert result["results"] == []
    assert "note" in result


def test_image_analysis_round_trip():
    store.record_image_analysis(
        "sample.jpg", "cell culture, confluent monolayer", "no cracks or discoloration found"
    )
    result = store.search_past_image_analyses("confluent monolayer")
    assert len(result["results"]) == 1
    assert result["results"][0]["image_path"] == "sample.jpg"


def test_image_analysis_search_includes_human_label():
    store.record_image_analysis("sample2.jpg", "yellow-tinted media", "discoloration at edge")
    # M5 will attach this via the review queue; simulate it here to prove
    # the search covers the label column too.
    with store._connect() as conn:
        conn.execute("UPDATE image_analyses SET human_label = ? WHERE image_path = ?", ("confirmed contamination", "sample2.jpg"))

    result = store.search_past_image_analyses("confirmed contamination")
    assert len(result["results"]) == 1


def test_environmental_state_found_when_fresh():
    store.log_environmental_state("bench-2", "Bunsen burner active", "user-x", ttl_hours=2)
    result = store.get_environmental_state("bench-2")
    assert result["found"] is True
    assert "Bunsen burner" in result["description"]


def test_environmental_state_expired_reads_as_unknown_not_safe():
    store.log_environmental_state("bench-3", "centrifuge running", "user-y", ttl_hours=-1)
    result = store.get_environmental_state("bench-3")
    assert result["found"] is False
    assert result["reason"] == "expired"


def test_environmental_state_never_logged_is_explicit():
    result = store.get_environmental_state("bench-never-used")
    assert result["found"] is False
    assert "no environmental state" in result["reason"]


def test_sop_handbook_finds_relevant_entry():
    result = search_sop_handbook("formaldehyde spill disposal")
    assert result["results"]
    assert any("chemical" in r["source"] for r in result["results"])


def test_sop_handbook_finds_laser_entry():
    result = search_sop_handbook("infrared laser goggles")
    assert result["results"]
    assert any("laser" in r["source"] for r in result["results"])


def test_sop_handbook_no_match_is_explicit():
    result = search_sop_handbook("nebula spectroscopy telescope calibration exoplanet")
    assert result["results"] == []
    assert "note" in result
