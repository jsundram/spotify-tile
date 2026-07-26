"""Spotify Web API client (Client Credentials flow).

The bearer token is held only in memory.  Raw responses are returned as dicts
so the cache can preserve them verbatim.
"""

from __future__ import annotations

import os
import time

import httpx

TOKEN_URL = "https://accounts.spotify.com/api/token"
API_BASE = "https://api.spotify.com/v1"


class SpotifyError(RuntimeError):
    pass


class CredentialsMissingError(SpotifyError):
    def __init__(self) -> None:
        super().__init__(
            "Spotify credentials are not configured. Set SPOTIFY_CLIENT_ID and "
            "SPOTIFY_CLIENT_SECRET in the environment or in a local .env file."
        )


class AuthError(SpotifyError):
    pass


class ForbiddenError(SpotifyError):
    pass


class NotFoundError(SpotifyError):
    pass


class RateLimitedError(SpotifyError):
    def __init__(self, retry_after: float) -> None:
        self.retry_after = retry_after
        super().__init__(f"Spotify rate limit exceeded; retry after {retry_after:.0f}s.")


class SpotifyNetworkError(SpotifyError):
    pass


class SpotifyClient:
    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        *,
        timeout: float = 15.0,
        max_rate_limit_wait: float = 30.0,
    ) -> None:
        self._client_id = client_id or os.environ.get("SPOTIFY_CLIENT_ID", "")
        self._client_secret = client_secret or os.environ.get("SPOTIFY_CLIENT_SECRET", "")
        if not self._client_id or not self._client_secret:
            raise CredentialsMissingError()
        self._http = httpx.Client(timeout=timeout)
        self._token: str | None = None
        self._token_expires_at: float = 0.0
        self._max_rate_limit_wait = max_rate_limit_wait

    # -- auth -----------------------------------------------------------
    def _ensure_token(self) -> str:
        if self._token and time.monotonic() < self._token_expires_at - 30:
            return self._token
        try:
            resp = self._http.post(
                TOKEN_URL,
                data={"grant_type": "client_credentials"},
                auth=(self._client_id, self._client_secret),
            )
        except httpx.HTTPError as exc:
            raise SpotifyNetworkError(f"Could not reach Spotify token endpoint: {exc}") from exc
        if resp.status_code in (400, 401):
            raise AuthError(
                "Spotify rejected the client credentials (HTTP "
                f"{resp.status_code}). Check SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET."
            )
        resp.raise_for_status()
        payload = resp.json()
        self._token = payload["access_token"]
        self._token_expires_at = time.monotonic() + float(payload.get("expires_in", 3600))
        return self._token

    # -- endpoints ------------------------------------------------------
    def get_track(self, track_id: str) -> dict:
        return self._get(f"/tracks/{track_id}", f"track {track_id}")

    def get_audio_features(self, track_id: str) -> dict:
        raw = self._get(f"/audio-features/{track_id}", f"audio features for {track_id}")
        if raw is None:
            raise SpotifyError(f"Spotify returned null audio features for track {track_id}.")
        return raw

    def get_playlist(self, playlist_id: str) -> dict:
        fields = "id,name,description,owner(display_name),external_urls,images"
        return self._get(
            f"/playlists/{playlist_id}?{httpx.QueryParams({'fields': fields})}",
            f"playlist {playlist_id}",
        )

    def get_playlist_items(self, playlist_id: str) -> list[dict]:
        """Return all track objects in a playlist (paged; episodes/local files skipped)."""
        items: list[dict] = []
        params = httpx.QueryParams(
            {"limit": 100, "offset": 0, "fields": "items(track),next,total"}
        )
        path = f"/playlists/{playlist_id}/tracks?{params}"
        while True:
            page = self._get(path, f"playlist {playlist_id} tracks")
            for item in page.get("items", []):
                track = item.get("track")
                if track and track.get("type") == "track" and track.get("id"):
                    items.append(track)
            next_url = page.get("next")
            if not next_url:
                return items
            path = next_url.removeprefix(API_BASE)

    def search_track(self, query: str, *, limit: int = 5) -> list[dict]:
        params = httpx.QueryParams({"q": query, "type": "track", "limit": limit})
        raw = self._get(f"/search?{params}", f"search for {query!r}")
        return raw.get("tracks", {}).get("items", [])

    def search_album(self, query: str, *, limit: int = 10) -> list[dict]:
        params = httpx.QueryParams({"q": query, "type": "album", "limit": limit})
        raw = self._get(f"/search?{params}", f"album search for {query!r}")
        return raw.get("albums", {}).get("items", [])

    def get_album(self, album_id: str) -> dict:
        """Full album object, including a (simplified, popularity-free) track list."""
        return self._get(f"/albums/{album_id}", f"album {album_id}")

    def get_tracks(self, track_ids: list[str]) -> list[dict]:
        """Full track objects (which carry ``popularity``) for the given ids.

        The Spotify batch endpoint accepts up to 50 ids per call; longer lists
        are fetched in chunks and concatenated in order.
        """
        out: list[dict] = []
        for start in range(0, len(track_ids), 50):
            batch = track_ids[start : start + 50]
            raw = self._get(f"/tracks?ids={','.join(batch)}", f"{len(batch)} tracks")
            out.extend(t for t in raw.get("tracks", []) if t)
        return out

    def _get(self, path: str, what: str, _retries: int = 2) -> dict:
        token = self._ensure_token()
        try:
            resp = self._http.get(f"{API_BASE}{path}", headers={"Authorization": f"Bearer {token}"})
        except httpx.HTTPError as exc:
            raise SpotifyNetworkError(f"Network failure fetching {what}: {exc}") from exc
        if resp.status_code == 401:
            raise AuthError(f"Spotify rejected the access token while fetching {what} (401).")
        if resp.status_code == 403:
            raise ForbiddenError(
                f"Spotify returned 403 for {what}. This endpoint may be unavailable to "
                "your app (audio-features access is restricted for apps created after "
                "November 2024). Use cached fixtures / --offline instead."
            )
        if resp.status_code == 404:
            raise NotFoundError(f"Spotify does not know {what} (404).")
        if resp.status_code == 429:
            retry_after = float(resp.headers.get("Retry-After", "1"))
            if _retries > 0 and retry_after <= self._max_rate_limit_wait:
                time.sleep(retry_after)
                return self._get(path, what, _retries - 1)
            raise RateLimitedError(retry_after)
        resp.raise_for_status()
        return resp.json()

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> SpotifyClient:  # noqa: PYI034
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
