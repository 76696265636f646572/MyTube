import { ref } from "vue";

import { fetchJson } from "./useApi";
import { useNotifications } from "./useNotifications";

const speakers = ref([]);
let initialized = false;
let initPromise = null;

async function refreshSonos() {
  speakers.value = await fetchJson("/api/sonos/speakers");
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
      notifySuccess("Playback started", `Streaming to ${ip}.`);
      return true;
    } catch (error) {
      notifyError("Could not start Sonos playback", error);
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
      await refreshSonos();
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
      await refreshSonos();
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
      return speakers.value.map((s) => (s.ip === ip ? { ...s, volume: vol } : s));
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
    playOnSpeaker,
    groupSpeaker,
    ungroupSpeaker,
    setSpeakerVolume,
  };
}

export function initializeSonosState() {
  if (initialized) return initPromise ?? Promise.resolve();
  initialized = true;
  initPromise = refreshSonos().then(() => {});
  return initPromise;
}
