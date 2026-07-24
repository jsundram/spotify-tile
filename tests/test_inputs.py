import pytest

from geomusic.inputs import InputError, id_flags, parse_track_input

TRACK_ID = "6Jv7kjGkhY2fT4yuBF3aTz"


@pytest.mark.parametrize(
    "value",
    [
        TRACK_ID,
        f"https://open.spotify.com/track/{TRACK_ID}",
        f"https://open.spotify.com/track/{TRACK_ID}?si=abc123",
        f"https://open.spotify.com/intl-de/track/{TRACK_ID}?si=abc",
        f"spotify:track:{TRACK_ID}",
        f"  {TRACK_ID}  ",
    ],
)
def test_accepted_forms(value):
    assert parse_track_input(value) == TRACK_ID


@pytest.mark.parametrize(
    "value",
    [
        "",
        "not-an-id",
        "https://open.spotify.com/album/1AhDOtG9vPSOmsWgNW0BEY",
        "https://open.spotify.com/playlist/1AhDOtG9vPSOmsWgNW0BEY",
        "spotify:album:1AhDOtG9vPSOmsWgNW0BEY",
        "spotify:track:tooShort",
        "https://example.com/track/6Jv7kjGkhY2fT4yuBF3aTz",
        "6Jv7kjGkhY2fT4yuBF3aT",  # 21 chars
        "6Jv7kjGkhY2fT4yuBF3aTz!",  # bad char
    ],
)
def test_rejected_forms(value):
    with pytest.raises(InputError):
        parse_track_input(value)


def test_id_flags_published_examples():
    assert id_flags("5ruz") == (True, False, False, False)
    assert id_flags("76G5") == (True, True, False, True)
    assert id_flags("6Jv7kjGkhY2fT4yuBF3aTz") == (True, False, False, True)
    assert id_flags("0Z57YWES04xGh3AImDz6Qr") == (True, False, True, True)
    assert id_flags("4U45aEWtQhrm8A5mxPaFZ7") == (True, False, True, True)
    assert id_flags("35Ki") == (True, True, False, False)
