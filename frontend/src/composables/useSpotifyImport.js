import { fetchJson } from "./useApi";

const SPOTIFY_PLAYLIST_HOSTS = new Set(["open.spotify.com", "www.open.spotify.com"]);

export function isSpotifyPlaylistUrl(rawUrl) {
  if (typeof rawUrl !== "string") return false;
  const trimmed = rawUrl.trim();
  if (!trimmed) return false;
  let parsed;
  try {
    parsed = new URL(trimmed);
  } catch {
    return false;
  }
  const host = parsed.hostname.toLowerCase();
  if (!SPOTIFY_PLAYLIST_HOSTS.has(host)) return false;
  const parts = parsed.pathname.split("/").filter(Boolean);
  return parts.length >= 2 && parts[0] === "playlist";
}

export function canonicalSpotifyPlaylistUrl(rawUrl) {
  const parsed = new URL(rawUrl.trim());
  const parts = parsed.pathname.split("/").filter(Boolean);
  if (parts.length >= 2 && parts[0] === "playlist") {
    return `https://open.spotify.com/playlist/${parts[1]}`;
  }
  return rawUrl.trim();
}

export async function importSpotifyPlaylist(url) {
  return fetchJson("/api/spotify/import", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ url }),
  });
}

export async function fetchSpotifyReview(playlistId) {
  return fetchJson(`/api/playlists/${playlistId}/spotify-review`);
}

export async function searchSpotifyEntry(playlistId, entryId, limit = 10) {
  return fetchJson(`/api/playlists/${playlistId}/spotify-search`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ entry_id: entryId, limit }),
  });
}

export async function selectSpotifyEntryResult(playlistId, entryId, result) {
  return fetchJson(`/api/playlists/${playlistId}/spotify-select`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ entry_id: entryId, result }),
  });
}
