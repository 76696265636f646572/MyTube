<template>
  <UApp>
    <div class="min-h-screen bg-neutral-950 text-neutral-100 p-3 flex flex-col gap-3">
      <TopBar
        :search-text="searchText"
        :search-results="searchResults"
        @add-url="onAddUrl"
        @play-url="onPlayUrl"
        @search="onYoutubeSearch"
        @search-text-change="onSearchTextChange"
      />

      <div class="grid gap-3 xl:grid-cols-[260px_minmax(0,1fr)_320px]">
        <SidebarPlaylists
          :playlists="filteredPlaylists"
          :active-playlist-id="activePlaylistId"
          @create-playlist="onCreatePlaylist"
          @select-playlist="onSelectPlaylist"
          @queue-playlist="onQueuePlaylist"
        />

        <main class="grid gap-3 min-h-0 xl:grid-rows-[minmax(280px,1fr)_minmax(220px,1fr)]">
          <QueuePanel
            :queue="filteredQueue"
            :active-playlist-id="activePlaylistId"
            @remove="onRemoveQueueItem"
            @reorder="onReorderQueueItem"
            @save-to-playlist="onSaveQueueToPlaylist"
          />
          <HistoryPanel :history="filteredHistory" />
        </main>

        <SonosPanel
          :speakers="speakers"
          @refresh="refreshSonos"
          @play="playOnSpeaker"
          @group="groupSpeaker"
          @ungroup="ungroupSpeaker"
          @set-volume="setSpeakerVolume"
        />
      </div>

      <PlayerBar :state="playbackState" @skip="skipCurrent" />
    </div>
  </UApp>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from "vue";

import HistoryPanel from "./components/HistoryPanel.vue";
import PlayerBar from "./components/PlayerBar.vue";
import QueuePanel from "./components/QueuePanel.vue";
import SidebarPlaylists from "./components/SidebarPlaylists.vue";
import SonosPanel from "./components/SonosPanel.vue";
import TopBar from "./components/TopBar.vue";
import { fetchJson } from "./composables/useApi";

const queue = ref([]);
const history = ref([]);
const playlists = ref([]);
const speakers = ref([]);
const playbackState = ref({
  mode: "idle",
  now_playing_title: null,
  duration_seconds: null,
  elapsed_seconds: null,
  progress_percent: null,
  stream_url: null,
});
const searchText = ref("");
const searchResults = ref([]);
const activePlaylistId = ref(null);

let fastPollTimer = null;
let regularPollTimer = null;
let sonosPollTimer = null;

const filteredQueue = computed(() => {
  if (!searchText.value.trim()) return queue.value;
  const needle = searchText.value.toLowerCase();
  return queue.value.filter((item) => {
    const haystack = `${item.title || ""} ${item.source_url || ""} ${item.channel || ""}`.toLowerCase();
    return haystack.includes(needle);
  });
});

const filteredHistory = computed(() => {
  if (!searchText.value.trim()) return history.value;
  const needle = searchText.value.toLowerCase();
  return history.value.filter((item) => {
    const haystack = `${item.title || ""} ${item.source_url || ""} ${item.status || ""}`.toLowerCase();
    return haystack.includes(needle);
  });
});

const filteredPlaylists = computed(() => {
  if (!searchText.value.trim()) return playlists.value;
  const needle = searchText.value.toLowerCase();
  return playlists.value.filter((item) => {
    const haystack = `${item.title || ""} ${item.channel || ""} ${item.kind || ""}`.toLowerCase();
    return haystack.includes(needle);
  });
});

async function refreshCore() {
  const [queueData, historyData, stateData, playlistsData] = await Promise.all([
    fetchJson("/queue"),
    fetchJson("/history"),
    fetchJson("/state"),
    fetchJson("/playlists"),
  ]);
  queue.value = queueData;
  history.value = historyData;
  playbackState.value = stateData;
  playlists.value = playlistsData;
}

async function refreshSonos() {
  speakers.value = await fetchJson("/sonos/speakers");
}

async function onAddUrl(url) {
  await fetchJson("/queue/add", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ url }),
  });
  await refreshCore();
}

async function onPlayUrl(url) {
  await fetchJson("/queue/play-now", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ url }),
  });
  await refreshCore();
}

async function onYoutubeSearch(query) {
  if (!query.trim()) {
    searchResults.value = [];
    return;
  }
  const payload = await fetchJson(`/search/youtube?q=${encodeURIComponent(query)}&limit=10`);
  searchResults.value = payload.results || [];
}

function onSearchTextChange(value) {
  searchText.value = value;
}

async function onRemoveQueueItem(itemId) {
  await fetchJson(`/queue/${itemId}`, { method: "DELETE" });
  await refreshCore();
}

async function onReorderQueueItem({ itemId, newPosition }) {
  await fetchJson(`/queue/${itemId}/reorder`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ new_position: newPosition }),
  });
  await refreshCore();
}

async function onCreatePlaylist(title) {
  const created = await fetchJson("/playlists/custom", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ title }),
  });
  activePlaylistId.value = created.id;
  await refreshCore();
}

function onSelectPlaylist(playlistId) {
  activePlaylistId.value = playlistId;
}

async function onQueuePlaylist(playlistId) {
  await fetchJson(`/playlists/${playlistId}/queue`, { method: "POST" });
  await refreshCore();
}

async function onSaveQueueToPlaylist(item) {
  if (!activePlaylistId.value) {
    return;
  }
  await fetchJson(`/playlists/${activePlaylistId.value}/entries`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ url: item.source_url }),
  });
  await refreshCore();
}

async function skipCurrent() {
  await fetchJson("/queue/skip", { method: "POST" });
  await refreshCore();
}

async function playOnSpeaker(ip) {
  await fetchJson("/sonos/play", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ speaker_ip: ip }),
  });
}

async function groupSpeaker({ coordinatorIp, memberIp }) {
  await fetchJson("/sonos/group", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ coordinator_ip: coordinatorIp, member_ip: memberIp }),
  });
  await refreshSonos();
}

async function ungroupSpeaker(ip) {
  await fetchJson("/sonos/ungroup", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ speaker_ip: ip }),
  });
  await refreshSonos();
}

async function setSpeakerVolume({ ip, volume }) {
  await fetchJson("/sonos/volume", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ speaker_ip: ip, volume }),
  });
}

onMounted(async () => {
  await Promise.all([refreshCore(), refreshSonos()]);
  fastPollTimer = setInterval(async () => {
    playbackState.value = await fetchJson("/state");
  }, 1000);
  regularPollTimer = setInterval(refreshCore, 4000);
  sonosPollTimer = setInterval(refreshSonos, 8000);
});

onUnmounted(() => {
  if (fastPollTimer) clearInterval(fastPollTimer);
  if (regularPollTimer) clearInterval(regularPollTimer);
  if (sonosPollTimer) clearInterval(sonosPollTimer);
});
</script>
