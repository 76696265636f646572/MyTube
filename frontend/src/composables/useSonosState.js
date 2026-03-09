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
    } catch (error) {
      notifyError("Could not start Sonos playback", error);
    }
  }

  async function groupSpeaker({ coordinatorIp, memberIp }) {
    try {
      await fetchJson("/api/sonos/group", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ coordinator_ip: coordinatorIp, member_ip: memberIp }),
      });
      await refreshSonos();
      notifySuccess("Speaker grouped", `${memberIp} joined ${coordinatorIp}.`);
    } catch (error) {
      notifyError("Could not group speaker", error);
    }
  }

  async function ungroupSpeaker(ip) {
    try {
      await fetchJson("/api/sonos/ungroup", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ speaker_ip: ip }),
      });
      await refreshSonos();
      notifySuccess("Speaker ungrouped", `${ip} left the group.`);
    } catch (error) {
      notifyError("Could not ungroup speaker", error);
    }
  }

  async function setSpeakerVolume({ ip, volume }) {
    try {
      await fetchJson("/api/sonos/volume", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ speaker_ip: ip, volume }),
      });
    } catch (error) {
      notifyError("Could not set volume", error);
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
