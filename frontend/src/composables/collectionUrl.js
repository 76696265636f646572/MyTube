export const SOURCE_LABELS = {
  youtube: "YouTube",
  vimeo: "Vimeo",
  dailymotion: "Dailymotion",
  bilibili: "Bilibili",
  peertube: "PeerTube",
  soundcloud: "SoundCloud",
  bandcamp: "Bandcamp",
  audiomack: "Audiomack",
  mixcloud: "Mixcloud",
  hearthis: "HearThis",
  boomplay: "Boomplay",
  anghami: "Anghami",
  jamendo: "Jamendo",
  archive: "Internet Archive",
  fma: "Free Music Archive",
  housemixes: "House-Mixes",
  tracklists1001: "1001Tracklists",
  nts: "NTS",
  applepodcasts: "Apple Podcasts",
  tunein: "TuneIn",
  podbean: "Podbean",
  spreaker: "Spreaker",
  tiktok: "TikTok",
  twitch: "Twitch",
  facebook: "Facebook",
};

const TYPE_LABELS = {
  playlist: "playlist",
  album: "album",
  channel: "channel",
  artist: "artist",
  tag: "tag",
  likes: "likes",
  tracks: "tracks",
  show: "show",
  podcast: "podcast",
  videos: "videos",
  collection: "collection",
};

function normalizeHost(hostname) {
  return String(hostname || "").toLowerCase().replace(/^www\./, "");
}

function classifySource(host) {
  if (host.endsWith("youtube.com") || host.endsWith("youtu.be")) return "youtube";
  if (host.endsWith("vimeo.com")) return "vimeo";
  if (host.endsWith("dailymotion.com")) return "dailymotion";
  if (host.endsWith("bilibili.com")) return "bilibili";
  if (host.endsWith("soundcloud.com")) return "soundcloud";
  if (host.endsWith("bandcamp.com")) return "bandcamp";
  if (host.endsWith("audiomack.com")) return "audiomack";
  if (host.endsWith("mixcloud.com")) return "mixcloud";
  if (host.endsWith("hearthis.at")) return "hearthis";
  if (host.endsWith("boomplay.com")) return "boomplay";
  if (host.endsWith("anghami.com")) return "anghami";
  if (host.endsWith("jamendo.com")) return "jamendo";
  if (host.endsWith("archive.org")) return "archive";
  if (host.endsWith("freemusicarchive.org")) return "fma";
  if (host.endsWith("house-mixes.com")) return "housemixes";
  if (host.endsWith("1001tracklists.com")) return "tracklists1001";
  if (host.endsWith("nts.live")) return "nts";
  if (host.endsWith("podcasts.apple.com")) return "applepodcasts";
  if (host.endsWith("tunein.com")) return "tunein";
  if (host.endsWith("podbean.com")) return "podbean";
  if (host.endsWith("spreaker.com")) return "spreaker";
  if (host.endsWith("tiktok.com")) return "tiktok";
  if (host.endsWith("twitch.tv")) return "twitch";
  if (host.endsWith("facebook.com")) return "facebook";
  if (host.includes(".") && host.split(".").length > 2) return "peertube";
  return null;
}

function sourceLabelFor(source, host) {
  if (source && SOURCE_LABELS[source]) return SOURCE_LABELS[source];
  const root = String(host || "").split(".")[0];
  return root ? `${root.charAt(0).toUpperCase()}${root.slice(1)}` : "Source";
}

function genericPathType(pathname) {
  const p = pathname.toLowerCase();
  if (/(^|\/)(playlist|playlists)(\/|$)/.test(p)) return "playlist";
  if (/(^|\/)(album|albums)(\/|$)/.test(p)) return "album";
  if (/(^|\/)(channel|channels)(\/|$)/.test(p)) return "channel";
  if (/(^|\/)(artist|artists)(\/|$)/.test(p)) return "artist";
  if (/(^|\/)(tag|tags)(\/|$)/.test(p)) return "tag";
  if (/(^|\/)(likes)(\/|$)/.test(p)) return "likes";
  if (/(^|\/)(tracks)(\/|$)/.test(p)) return "tracks";
  if (/(^|\/)(show|shows)(\/|$)/.test(p)) return "show";
  if (/(^|\/)(podcast|podcasts)(\/|$)/.test(p)) return "podcast";
  if (/(^|\/)(videos|uploads)(\/|$)/.test(p)) return "videos";
  if (/(^|\/)(set|sets|collection|collections|music)(\/|$)/.test(p)) return "collection";
  return null;
}

function classifyType(source, parsed) {
  const pathname = parsed.pathname || "/";
  const query = parsed.searchParams;
  const lowerPath = pathname.toLowerCase();

  if (source === "youtube") {
    if (lowerPath.includes("/watch")) return query.get("list") ? "playlist" : null;
    if (lowerPath.includes("/playlist") && query.get("list")) return "playlist";
    if (/^\/(@[^/]+|channel\/[^/]+|c\/[^/]+|user\/[^/]+)\/(videos|shorts|streams)?\/?$/.test(lowerPath))
      return "channel";
    const segments = lowerPath.split("/").filter(Boolean);
    if (segments.length === 1) {
      const blocked = new Set(["watch", "playlist", "results", "feed", "shorts", "live"]);
      if (!blocked.has(segments[0])) return "channel";
    }
  }
  if (source === "vimeo") {
    if (lowerPath.startsWith("/showcase/")) return "playlist";
    if (lowerPath.startsWith("/channels/")) return "channel";
  }
  if (source === "dailymotion" && lowerPath.startsWith("/playlist/")) return "playlist";
  if (source === "bilibili") {
    if (lowerPath.startsWith("/bangumi/play/ss")) return "playlist";
    if (lowerPath.includes("/channel/collectiondetail") || query.get("sid")) return "collection";
  }
  if (source === "soundcloud") {
    if (/^\/[^/]+\/sets\/[^/]+/.test(lowerPath)) return "playlist";
    if (/^\/[^/]+\/tracks\/?$/.test(lowerPath)) return "tracks";
    if (/^\/[^/]+\/likes\/?$/.test(lowerPath)) return "likes";
    if (/^\/[^/]+\/?$/.test(lowerPath)) return "artist";
  }
  if (source === "bandcamp") {
    if (lowerPath.startsWith("/album/")) return "album";
    if (lowerPath === "/music" || lowerPath === "/music/") return "artist";
  }
  if (source === "audiomack") {
    if (lowerPath.includes("/album/")) return "album";
    if (lowerPath.includes("/playlist/")) return "playlist";
  }
  if (source === "mixcloud") {
    if (lowerPath.includes("/playlists/")) return "playlist";
    if (lowerPath.startsWith("/tag/")) return "tag";
    if (/^\/[^/]+\/?$/.test(lowerPath)) return "tracks";
  }
  if (source === "hearthis") {
    if (/^\/[^/]+\/set\/[^/]+/.test(lowerPath)) return "playlist";
    if (/^\/[^/]+\/?$/.test(lowerPath)) return "tracks";
  }
  if (source === "boomplay") {
    if (lowerPath.startsWith("/albums/")) return "album";
    if (lowerPath.startsWith("/playlists/")) return "playlist";
  }
  if (source === "anghami") {
    if (lowerPath.startsWith("/playlist/")) return "playlist";
    if (lowerPath.startsWith("/album/")) return "album";
  }
  if (source === "jamendo") {
    if (lowerPath.startsWith("/album/")) return "album";
    if (lowerPath.startsWith("/artist/")) return "artist";
  }
  if (source === "archive" && lowerPath.startsWith("/details/")) return "collection";
  if (source === "fma") {
    if (lowerPath.startsWith("/curator/")) return "playlist";
    if (lowerPath.startsWith("/music/")) return "album";
  }
  if (source === "housemixes") {
    if (lowerPath.includes("/playlists")) return "playlist";
    if (lowerPath.includes("/profile/")) return "tracks";
  }
  if (source === "tracklists1001") {
    if (lowerPath.startsWith("/tracklist/")) return "playlist";
    if (lowerPath.startsWith("/dj/")) return "artist";
  }
  if (source === "nts" && lowerPath.startsWith("/shows/")) return "show";
  if (source === "applepodcasts" && lowerPath.includes("/podcast/")) return "podcast";
  if (source === "tunein" && lowerPath.startsWith("/podcasts/")) return "podcast";
  if (source === "podbean") return "podcast";
  if (source === "spreaker" && lowerPath.startsWith("/show/")) return "show";
  if (source === "tiktok") {
    if (/^\/@[^/]+\/playlist\/[^/]+/.test(lowerPath)) return "playlist";
    if (/^\/@[^/]+\/?$/.test(lowerPath)) return "tracks";
  }
  if (source === "twitch" && /^\/[^/]+\/videos\/?$/.test(lowerPath)) return "videos";
  if (source === "facebook" && /^\/[^/]+\/videos\/?$/.test(lowerPath)) return "videos";

  return genericPathType(pathname);
}

export function classifyCollectionUrl(url) {
  const trimmed = String(url || "").trim();
  if (!trimmed) return { isCollection: false, source: null, sourceLabel: "Source", collectionType: null, url: null };

  let parsed;
  try {
    parsed = new URL(trimmed);
  } catch (_) {
    return { isCollection: false, source: null, sourceLabel: "Source", collectionType: null, url: trimmed };
  }

  const host = normalizeHost(parsed.hostname);
  const source = classifySource(host);
  const collectionType = classifyType(source, parsed);
  const sourceLabel = sourceLabelFor(source, host);
  return {
    isCollection: Boolean(collectionType),
    source,
    sourceLabel,
    collectionType,
    url: trimmed,
  };
}

export function canonicalCollectionUrl(url) {
  const trimmed = String(url || "").trim();
  if (!trimmed) return null;
  try {
    const parsed = new URL(trimmed);
    const host = normalizeHost(parsed.hostname);
    const source = classifySource(host);
    const lowerPath = (parsed.pathname || "").toLowerCase();
    const listId = parsed.searchParams.get("list");
    if (source === "youtube" && listId) {
      return `https://www.youtube.com/playlist?list=${listId}`;
    }
  } catch (_) {
    return trimmed;
  }
  return trimmed;
}

export function collectionActionLabels(info) {
  const source = info?.sourceLabel || "Source";
  const typeKey = info?.collectionType || "collection";
  const typeLabel = TYPE_LABELS[typeKey] || "collection";
  return {
    queue: `Queue ${source} ${typeLabel}`,
    play: `Play ${source} ${typeLabel}`,
    import: `Import ${source} ${typeLabel}`,
  };
}
