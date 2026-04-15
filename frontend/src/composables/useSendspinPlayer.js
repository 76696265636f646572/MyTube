import { computed, onUnmounted, ref } from "vue";

import { onEventBus } from "./eventBus";
import { fetchJson } from "./useApi";

const STORAGE_KEY_CLIENT_ID = "airwave:sendspin:client-id";
const STORAGE_KEY_VOLUME = "airwave:sendspin:volume";
const STORAGE_KEY_STATIC_DELAY = "airwave:sendspin:static-delay";
const DEFAULT_VOLUME = 80;

function generateUUID() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
  });
}

function readStored(key, fallback = null) {
  if (typeof window === "undefined") return fallback;
  try {
    const val = window.localStorage.getItem(key);
    return val != null ? val : fallback;
  } catch {
    return fallback;
  }
}

function writeStored(key, value) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(key, String(value));
  } catch {
    /* ignore */
  }
}

function getOrCreateClientId() {
  let id = readStored(STORAGE_KEY_CLIENT_ID);
  if (!id) {
    id = generateUUID();
    writeStored(STORAGE_KEY_CLIENT_ID, id);
  }
  return id;
}

const sendspinClients = ref([]);
const sendspinGroup = ref({ volume: 0, muted: false });
const sendspinPort = ref(8927);

function applySendspinSnapshot(snapshot) {
  if (!snapshot || typeof snapshot !== "object") return;
  if (snapshot.sendspin && typeof snapshot.sendspin === "object") {
    if (Array.isArray(snapshot.sendspin.clients)) {
      sendspinClients.value = snapshot.sendspin.clients;
    }
    if (snapshot.sendspin.group && typeof snapshot.sendspin.group === "object") {
      sendspinGroup.value = snapshot.sendspin.group;
    }
    if (typeof snapshot.sendspin.port === "number") {
      sendspinPort.value = snapshot.sendspin.port;
    }
  }
}

let snapshotUnsub = null;

export function initializeSendspinState() {
  if (snapshotUnsub) return;
  snapshotUnsub = onEventBus("ws:snapshot", (payload) => {
    applySendspinSnapshot(payload);
  });
  fetchJson("/api/sendspin/clients").then((data) => {
    if (data && typeof data.port === "number") {
      sendspinPort.value = data.port;
    }
  }).catch(() => {});
}

/**
 * Wraps @sendspin/sendspin-js SendspinPlayer with Vue reactive state.
 */
export function useSendspinPlayer() {
  const isConnected = ref(false);
  const isPlaying = ref(false);
  const volume = ref(Number(readStored(STORAGE_KEY_VOLUME, DEFAULT_VOLUME)));
  const muted = ref(false);
  const currentFormat = ref(null);
  const serverMetadata = ref(null);
  const groupState = ref(null);
  const syncInfo = ref(null);
  const correctionMode = ref("sync");
  const staticDelay = ref(Number(readStored(STORAGE_KEY_STATIC_DELAY, 0)));

  let player = null;
  let SendspinPlayerClass = null;

  const isLocalPlaybackActive = computed(() => isConnected.value && isPlaying.value);

  const localPlaybackSessionDeps = computed(() => ({
    wantsLocal: isConnected.value,
    audioPaused: !isPlaying.value,
  }));

  const localVolume = computed({
    get: () => volume.value / 100,
    set: (v) => setVolume(Math.round(v * 100)),
  });

  const isMuted = computed(() => muted.value || volume.value <= 0);

  function onStateChange(state) {
    isPlaying.value = state.isPlaying ?? false;
    volume.value = state.volume ?? volume.value;
    muted.value = state.muted ?? false;
    currentFormat.value = state.currentFormat ?? null;

    if (state.serverState?.metadata) {
      serverMetadata.value = state.serverState.metadata;
    }
    if (state.groupState) {
      groupState.value = state.groupState;
    }
    if (state.syncInfo) {
      syncInfo.value = state.syncInfo;
    }
  }

  async function ensurePlayerClass() {
    if (SendspinPlayerClass) return;
    const mod = await import("@sendspin/sendspin-js");
    SendspinPlayerClass = mod.SendspinPlayer;
  }

  async function connect() {
    await ensurePlayerClass();

    if (player) {
      player.disconnect("user_request");
      player = null;
    }

    const port = sendspinPort.value;
    const baseUrl = `${window.location.protocol}//${window.location.hostname}:${port}`;
    const clientId = getOrCreateClientId();
    const storedDelay = Number(readStored(STORAGE_KEY_STATIC_DELAY, 0));

    player = new SendspinPlayerClass({
      playerId: clientId,
      baseUrl,
      clientName: "Airwave Web Player",
      correctionMode: correctionMode.value,
      syncDelay: storedDelay,
      onStateChange,
    });

    await player.connect();
    isConnected.value = true;

    player.setVolume(volume.value);
    player.setMuted(muted.value);
  }

  function disconnect(reason = "user_request") {
    if (player) {
      player.disconnect(reason);
      player = null;
    }
    isConnected.value = false;
    isPlaying.value = false;
  }

  function setVolume(v) {
    const clamped = Math.max(0, Math.min(100, v));
    volume.value = clamped;
    writeStored(STORAGE_KEY_VOLUME, clamped);
    if (player) {
      player.setVolume(clamped);
    }
    if (clamped > 0) {
      muted.value = false;
      if (player) player.setMuted(false);
    }
  }

  function setMuted(m) {
    muted.value = m;
    if (player) {
      player.setMuted(m);
    }
  }

  function toggleMuted() {
    setMuted(!muted.value);
  }

  function setSyncDelay(ms) {
    staticDelay.value = ms;
    writeStored(STORAGE_KEY_STATIC_DELAY, ms);
    if (player) {
      player.setSyncDelay(ms);
    }
  }

  function setCorrectionMode(mode) {
    correctionMode.value = mode;
    if (player) {
      player.setCorrectionMode(mode);
    }
  }

  function localPlaybackStatus() {
    return {
      isLocalPlaybackActive: isConnected.value,
      isLocalPlaybackPaused: !isPlaying.value,
      isLocalPlaybackPlaying: isConnected.value && isPlaying.value,
      isLocalPlaybackStopped: !isConnected.value,
    };
  }

  function setLocalVolume(v01) {
    setVolume(Math.round(v01 * 100));
  }

  async function startLocalPlayback() {
    await connect();
  }

  function stopLocalPlayback() {
    disconnect();
  }

  function pauseLocalPlayback() {
    /* no-op: sendspin player doesn't pause locally */
  }

  async function resumeLocalPlayback() {
    if (!isConnected.value) {
      await connect();
    }
  }

  onUnmounted(() => {
    disconnect("shutdown");
  });

  return {
    isConnected,
    isPlaying,
    volume,
    muted,
    currentFormat,
    serverMetadata,
    groupState,
    syncInfo,
    correctionMode,
    staticDelay,

    connect,
    disconnect,
    setVolume,
    setMuted,
    toggleMuted,
    setSyncDelay,
    setCorrectionMode,
    localPlaybackStatus,

    isLocalPlaybackActive,
    localPlaybackSessionDeps,
    localVolume,
    isMuted,
    setLocalVolume,
    startLocalPlayback,
    stopLocalPlayback,
    pauseLocalPlayback,
    resumeLocalPlayback,

    sendspinClients,
    sendspinGroup,
  };
}
