import httpx
import pytest

from geomusic.spotify import (
    AuthError,
    CredentialsMissingError,
    ForbiddenError,
    NotFoundError,
    RateLimitedError,
    SpotifyClient,
)


@pytest.fixture
def creds(monkeypatch):
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "test-id")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "test-secret")


def make_client(handler) -> SpotifyClient:
    client = SpotifyClient("test-id", "test-secret")
    client._http = httpx.Client(transport=httpx.MockTransport(handler))
    return client


def token_response():
    return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})


def test_missing_credentials(monkeypatch):
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    monkeypatch.delenv("SPOTIFY_CLIENT_SECRET", raising=False)
    with pytest.raises(CredentialsMissingError):
        SpotifyClient()


def test_token_and_track(creds):
    def handler(request):
        if request.url.path == "/api/token":
            assert b"client_credentials" in request.read()
            return token_response()
        assert request.headers["Authorization"] == "Bearer tok"
        return httpx.Response(200, json={"id": "x", "name": "Song"})

    client = make_client(handler)
    assert client.get_track("x" * 22)["name"] == "Song"


def test_invalid_credentials(creds):
    client = make_client(lambda request: httpx.Response(401, json={}))
    with pytest.raises(AuthError):
        client.get_track("x" * 22)


@pytest.mark.parametrize("status,exc", [(403, ForbiddenError), (404, NotFoundError)])
def test_error_mapping(creds, status, exc):
    def handler(request):
        if request.url.path == "/api/token":
            return token_response()
        return httpx.Response(status, json={})

    with pytest.raises(exc):
        make_client(handler).get_track("x" * 22)


def test_rate_limit_retries_then_raises(creds, monkeypatch):
    sleeps = []
    monkeypatch.setattr("geomusic.spotify.time.sleep", sleeps.append)

    def handler(request):
        if request.url.path == "/api/token":
            return token_response()
        return httpx.Response(429, headers={"Retry-After": "3"}, json={})

    with pytest.raises(RateLimitedError) as info:
        make_client(handler).get_track("x" * 22)
    assert sleeps == [3.0, 3.0]  # two retries honored Retry-After
    assert info.value.retry_after == 3.0


def test_null_audio_features_rejected(creds):
    def handler(request):
        if request.url.path == "/api/token":
            return token_response()
        return httpx.Response(200, content=b"null", headers={"Content-Type": "application/json"})

    with pytest.raises(Exception, match="null audio features"):
        make_client(handler).get_audio_features("x" * 22)


def test_secret_never_in_error_messages(creds):
    def handler(request):
        if request.url.path == "/api/token":
            return token_response()
        return httpx.Response(403, json={})

    try:
        make_client(handler).get_track("x" * 22)
    except ForbiddenError as exc:
        assert "test-secret" not in str(exc)
