import httpx
import pytest

from geomusic.preview_features import PreviewAnalysisError, parse_key_mode, preview_url


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("String Quintet in C Major, Op. 42/2 G. 349: I. Andante con moto", (0, 1)),
        ("String Quintet in E-Flat Major, Op. 41/1 G. 346 “Alla Turca”: I. Allegro vivo", (3, 1)),
        ("String Quartet in F-Sharp Minor", (6, 0)),
        ("Quartet in Bb Major", (10, 1)),
        ("Sonata in C# minor", (1, 0)),
        ("String Quartet in E flat major", (3, 1)),
        # Spanish solfege (e.g. the Artaria Op. 8 album)
        ("Cuarteto Nº1 (G. 165) en Re Mayor: I. Allegro assai", (2, 1)),
        ("Cuarteto Nº2 (G. 166) en Do Menor: I. Moderato", (0, 0)),
        ("Cuarteto Nº3 (G. 167) en Mi Bemol Mayor: I. Largo", (3, 1)),
        ("Cuarteto Nº4 (G. 168) en Sol Menor: II. Grave", (7, 0)),
        # No key named
        ("Violin Concerto No. 1", None),
        ("O Holy Night", None),
    ],
)
def test_parse_key_mode(title, expected):
    assert parse_key_mode(title) == expected


# Embed page shaped like the real one: preview URL nested inside __NEXT_DATA__.
NEXT_DATA_HTML = (
    '<html><script id="__NEXT_DATA__" type="application/json">'
    '{"props":{"pageProps":{"state":{"data":{"entity":{'
    '"audioPreview":{"url":"https://p.scdn.co/mp3-preview/abc123"}}}}}}}'
    "</script></html>"
)
# No __NEXT_DATA__ script tag: exercises the raw-text fallback, whose capture
# is JSON-escaped (the escaped ampersand must come back as a literal "&").
FALLBACK_HTML = (
    '<html>{"audioPreview":{"url":'
    '"https://p.scdn.co/mp3-preview/x?a=1\\u0026b=2"}}</html>'
)
NO_PREVIEW_HTML = "<html><body>nothing here</body></html>"


def _client(html: str, status: int = 200) -> httpx.Client:
    transport = httpx.MockTransport(lambda req: httpx.Response(status, text=html))
    return httpx.Client(transport=transport)


def test_preview_url_next_data_path():
    with _client(NEXT_DATA_HTML) as client:
        assert preview_url("x", client) == "https://p.scdn.co/mp3-preview/abc123"


def test_preview_url_fallback_path_unescapes():
    with _client(FALLBACK_HTML) as client:
        assert preview_url("x", client) == "https://p.scdn.co/mp3-preview/x?a=1&b=2"


def test_preview_url_absent():
    with _client(NO_PREVIEW_HTML) as client:
        assert preview_url("x", client) is None


def test_preview_url_http_error_wrapped():
    with _client("oops", status=500) as client, pytest.raises(PreviewAnalysisError):
        preview_url("x", client)
