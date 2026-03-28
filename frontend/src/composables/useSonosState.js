import { ref } from "vue";

import { fetchJson } from "./useApi";
import { useNotifications } from "./useNotifications";

const SONOS_POLL_INTERVAL_MS = 5000;
const speakers = ref([]);
let initialized = false;
let initPromise = null;
let refreshPromise = null;
let pollIntervalId = null;
let autoRefreshEnabled = false;

async function refreshSonosRequest() {
  if (!refreshPromise) {
    refreshPromise = (async () => {
      const nextSpeakers = await fetchJson("/api/sonos/speakers");
      speakers.value = nextSpeakers;
      return nextSpeakers;
    })().finally(() => {
      refreshPromise = null;
    });
  }
  return refreshPromise;
}

async function refreshSonos(options = {}) {
  const { silent = false } = options;
  try {
    await refreshSonosRequest();
    return true;
  } catch (error) {
    if (!silent) {
      throw error;
    }
    return false;
  }
}

function stopSonosAutoRefresh() {
  autoRefreshEnabled = false;
  if (pollIntervalId != null && typeof window !== "undefined") {
    window.clearInterval(pollIntervalId);
  }
  pollIntervalId = null;
}

async function setSonosAutoRefreshEnabled(enabled) {
  autoRefreshEnabled = !!enabled;
  if (!autoRefreshEnabled) {
    stopSonosAutoRefresh();
    return;
  }

  await refreshSonos({ silent: true });
  if (!autoRefreshEnabled || pollIntervalId != null || typeof window === "undefined") {
    return;
  }

  pollIntervalId = window.setInterval(() => {
    void refreshSonos({ silent: true });
  }, SONOS_POLL_INTERVAL_MS);
}

export function useSonosState() {
  const { notifySuccess, notifyError } = useNotifications();

  async function refreshSonosManual() {
    try {
      await refreshSonos();
      notifySuccess("Sonos refreshed", "Speaker list updated.");
    } catch (error) {
      notifyError("Could not refresh Sonos", error);
    }
  }

  async function playOnSpeaker(ip) {
    try {
      await fetchJson("/api/sonos/play", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ speaker_ip: ip }),
      });
      await refreshSonos({ silent: true });
      notifySuccess("Playback started", `Streaming to ${ip}.`);
      return true;
    } catch (error) {
      notifyError("Could not start Sonos playback", error);
      return false;
    }
  }

  async function stopOnSpeaker(ip) {

    try {
      await fetchJson("/api/sonos/stop", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ speaker_ip: ip }),
      });
      await refreshSonos({ silent: true });
      notifySuccess("Playback stopped", `Stopped playback on ${ip}.`);
      return true;
    } catch (error) {
      notifyError("Could not stop Sonos playback", error);
      return false;
    }
  }
  async function groupSpeaker({ coordinatorIp, memberIp }, options = {}) {
    const { notifySuccessMessage = true } = options;
    try {
      await fetchJson("/api/sonos/group", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ coordinator_ip: coordinatorIp, member_ip: memberIp }),
      });
      await refreshSonos({ silent: true });
      if (notifySuccessMessage) {
        notifySuccess("Speaker grouped", `${memberIp} joined ${coordinatorIp}.`);
      }
      return true;
    } catch (error) {
      notifyError("Could not group speaker", error);
      return false;
    }
  }

  async function ungroupSpeaker(ip, options = {}) {
    const { notifySuccessMessage = true } = options;
    try {
      await fetchJson("/api/sonos/ungroup", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ speaker_ip: ip }),
      });
      await refreshSonos({ silent: true });
      if (notifySuccessMessage) {
        notifySuccess("Speaker ungrouped", `${ip} left the group.`);
      }
      return true;
    } catch (error) {
      notifyError("Could not ungroup speaker", error);
      return false;
    }
  }

  async function setSpeakerVolume({ ip, volume }) {
    const speaker = speakers.value.find((s) => s.ip === ip);
    const previousVolume = speaker?.volume;
    // Replace the speaker in the array so Vue reactivity updates the UI immediately
    function withVolume(vol) {
      return speakers.value.map((s) => ({
        ...s,
        volume: s.ip === ip ? vol : s.volume,
        group_members: Array.isArray(s.group_members)
          ? s.group_members.map((member) => (member.ip === ip ? { ...member, volume: vol } : member))
          : s.group_members,
      }));
    }
    speakers.value = withVolume(volume);
    try {
      await fetchJson("/api/sonos/volume", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ speaker_ip: ip, volume }),
      });
      return true;
    } catch (error) {
      speakers.value = withVolume(previousVolume ?? 0);
      notifyError("Could not set volume", error);
      return false;
    }
  }

  return {
    speakers,
    refreshSonosManual,
    setSonosAutoRefreshEnabled,
    playOnSpeaker,
    stopOnSpeaker,
    groupSpeaker,
    ungroupSpeaker,
    setSpeakerVolume,
  };
}

export function initializeSonosState() {
  if (initialized) return initPromise ?? Promise.resolve();
  initialized = true;
  initPromise = refreshSonos({ silent: true }).then(() => {});
  return initPromise;
}
