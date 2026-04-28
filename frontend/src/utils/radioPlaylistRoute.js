const PREFIX = "remote:radio:";

function safeDecodeURIComponent(s) {
  try {
    return decodeURIComponent(s);
  } catch {
    return s;
  }
}

function utf8BytesToBase64Url(bytes) {
  let binary = "";
  for (let i = 0; i < bytes.length; i += 1) {
    binary += String.fromCharCode(bytes[i]);
  }
  const b64 = btoa(binary);
  return b64.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function base64UrlToUtf8String(segment) {
  let b64 = segment.replace(/-/g, "+").replace(/_/g, "/");
  while (b64.length % 4) b64 += "=";
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  return new TextDecoder().decode(bytes);
}

/**
 * @param {{ artist: string, track: string, source_url?: string, provider?: string, title?: string, channel?: string }} seed
 * @returns {string} Full playlist route id (path segment)
 */
export function encodeRadioPlaylistId(seed) {
  const payload = JSON.stringify({
    artist: (seed.artist || "").trim(),
    track: (seed.track || "").trim(),
    source_url: seed.source_url != null ? String(seed.source_url).trim() : undefined,
    provider: seed.provider != null ? String(seed.provider).trim() : undefined,
    title: seed.title != null ? String(seed.title).trim() : undefined,
    channel: seed.channel != null ? String(seed.channel).trim() : undefined,
  });
  const bytes = new TextEncoder().encode(payload);
  return `${PREFIX}${utf8BytesToBase64Url(bytes)}`;
}

/**
 * @param {string} playlistId route param (may be URL-encoded)
 * @returns {{ artist: string, track: string, source_url?: string, provider?: string, title?: string, channel?: string } | null}
 */
export function decodeRadioPlaylistSeed(playlistId) {
  const raw = typeof playlistId === "string" ? safeDecodeURIComponent(playlistId.trim()) : "";
  if (!raw.startsWith(PREFIX)) return null;
  const segment = raw.slice(PREFIX.length);
  if (!segment) return null;
  try {
    const json = base64UrlToUtf8String(segment);
    const data = JSON.parse(json);
    if (!data || typeof data !== "object") return null;
    const artist = typeof data.artist === "string" ? data.artist.trim() : "";
    const track = typeof data.track === "string" ? data.track.trim() : "";
    if (!artist || !track) return null;
    const out = { artist, track };
    if (typeof data.source_url === "string" && data.source_url.trim()) out.source_url = data.source_url.trim();
    if (typeof data.provider === "string" && data.provider.trim()) out.provider = data.provider.trim();
    if (typeof data.title === "string" && data.title.trim()) out.title = data.title.trim();
    if (typeof data.channel === "string" && data.channel.trim()) out.channel = data.channel.trim();
    return out;
  } catch {
    return null;
  }
}

export function isRadioPlaylistRouteId(playlistId) {
  const raw = typeof playlistId === "string" ? safeDecodeURIComponent(playlistId.trim()) : "";
  return raw.startsWith(PREFIX);
}
