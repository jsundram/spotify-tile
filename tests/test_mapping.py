import pytest

from geomusic.config import DEFAULT_CONFIG
from geomusic.models import AudioFeatures
from geomusic.normalize import cell_seed, clamp, derive, remap
from geomusic.palettes import PITCH_NAMES, get_palette, load_palettes


def test_remap_and_clamp():
    assert remap(-30, (-60, 0), (0, 1)) == 0.5
    assert remap(-120, (-60, 0), (0.2, 1.0)) == 0.2  # clamped low
    assert remap(50, (-60, 0), (0.2, 1.0)) == 1.0  # clamped high
    assert clamp(5, 0, 1) == 1


def test_mode_to_composition(lover, judas):
    assert lover.features.mode == 1
    assert derive(lover, DEFAULT_CONFIG).composition == "square"
    assert judas.features.mode == 0
    assert derive(judas, DEFAULT_CONFIG).composition == "rect"


def test_lover_parameters(lover):
    p = derive(lover, DEFAULT_CONFIG)
    assert p.flags == (True, False, False, True)
    assert p.cell_count == 10
    assert p.key == 2
    assert p.pitch == "D"
    assert p.displaced  # instrumentalness 1.1e-5 > 0 (literal published rule)
    x0, x1 = DEFAULT_CONFIG.x_scale_range
    assert x0 <= p.x_scale <= x1


def test_instrumentalness_binary_condition(lover):
    features = lover.features.model_copy(update={"instrumentalness": 0.0})
    data = lover.model_copy(update={"features": features})
    assert not derive(data, DEFAULT_CONFIG).displaced


def test_pitch_class_labels():
    assert PITCH_NAMES[0] == "C"
    assert PITCH_NAMES[10] == "Bb"
    assert len(PITCH_NAMES) == 12


def test_all_twelve_palettes_present():
    palettes = load_palettes()
    assert sorted(palettes) == list(range(12))
    for palette in palettes.values():
        assert palette.background in palette.colors
        assert len(palette.colors) == 8
        for color in palette.colors:
            assert color.startswith("#") and len(color) == 7


def test_evidence_backed_backgrounds():
    # Backgrounds confirmed by reference posters (JPEG-shifted, so approximate).
    assert get_palette(2).background == "#ffd4d4"  # Lover / Sunset pink
    assert get_palette(1).background == "#1c6056"  # Holocene green
    assert get_palette(0).background == "#39295e"  # Bohemian Rhapsody purple
    assert get_palette(5).background == "#f7c96b"  # The Adults Are Talking yellow
    assert get_palette(10).background == "#b2c2d3"  # Judas / Vienna blue


def test_negative_key_rejected():
    with pytest.raises(ValueError, match="no detected key"):
        AudioFeatures(
            danceability=0.5, energy=0.5, key=-1, loudness=-10, mode=1,
            speechiness=0.05, acousticness=0.5, instrumentalness=0, liveness=0.1,
            valence=0.5, tempo=120, duration_ms=200000, time_signature=4,
        )


def test_cell_seed_deterministic_and_distinct():
    a = cell_seed("6Jv7kjGkhY2fT4yuBF3aTz", 0)
    assert a == cell_seed("6Jv7kjGkhY2fT4yuBF3aTz", 0)
    assert a != cell_seed("6Jv7kjGkhY2fT4yuBF3aTz", 1)
    assert a != cell_seed("4U45aEWtQhrm8A5mxPaFZ7", 0)
