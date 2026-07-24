"""Pydantic domain models for track metadata and audio features."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class TrackMetadata(BaseModel):
    id: str
    name: str
    artists: list[str]
    album: str
    spotify_url: str

    @classmethod
    def from_api(cls, raw: dict) -> TrackMetadata:
        return cls(
            id=raw["id"],
            name=raw["name"],
            artists=[a["name"] for a in raw.get("artists", [])],
            album=(raw.get("album") or {}).get("name", ""),
            spotify_url=(raw.get("external_urls") or {}).get(
                "spotify", f"https://open.spotify.com/track/{raw['id']}"
            ),
        )


class AudioFeatures(BaseModel):
    danceability: float = Field(ge=0.0, le=1.0)
    energy: float = Field(ge=0.0, le=1.0)
    key: int = Field(ge=-1, le=11)
    loudness: float
    mode: int = Field(ge=0, le=1)
    speechiness: float = Field(ge=0.0, le=1.0)
    acousticness: float = Field(ge=0.0, le=1.0)
    instrumentalness: float = Field(ge=0.0, le=1.0)
    liveness: float = Field(ge=0.0)
    valence: float = Field(ge=0.0, le=1.0)
    tempo: float = Field(ge=0.0)
    duration_ms: int = Field(gt=0)
    time_signature: int = Field(ge=0)

    @field_validator("key")
    @classmethod
    def key_known(cls, v: int) -> int:
        # Spotify uses -1 for "no key detected"; the mapping needs 0..11.
        if v < 0:
            raise ValueError("track has no detected key (key = -1); cannot map a palette")
        return v

    @classmethod
    def from_api(cls, raw: dict) -> AudioFeatures:
        missing = [k for k in cls.model_fields if raw.get(k) is None]
        if missing:
            raise ValueError(f"audio features response is missing fields: {missing}")
        return cls(**{k: raw[k] for k in cls.model_fields})


class TrackData(BaseModel):
    track: TrackMetadata
    features: AudioFeatures

    @classmethod
    def from_cache_doc(cls, doc: dict) -> TrackData:
        return cls(
            track=TrackMetadata.from_api(doc["track"]),
            features=AudioFeatures.from_api(doc["audio_features"]),
        )
