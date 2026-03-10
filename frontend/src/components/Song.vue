<template>
  <div class="group flex items-center gap-3 rounded-md border px-3 py-2 playlist-card">
    <img
      v-if="thumbnailSrc"
      :src="thumbnailSrc"
      :alt="item.title || 'Thumbnail'"
      class="h-14 w-24 shrink-0 rounded object-cover surface-elevated"
      loading="lazy"
      referrerpolicy="no-referrer"
    />
    <div class="min-w-0 flex-1">
      <p class="truncate text-sm font-medium">
        <template v-if="mode === 'queue' && item.queue_position != null">#{{ item.queue_position }} </template>
        {{ item.title || item.source_url }}
      </p>
      <div class="mt-0.5 flex items-center gap-1">
        <span
          v-if="sourceSiteLabel"
          class="rounded border border-neutral-600 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-muted"
        >
          {{ sourceSiteLabel }}
        </span>
        <span
          v-if="isLive"
          class="rounded border border-red-500/60 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-red-300"
        >
          LIVE
        </span>
      </div>
      <p v-if="showSecondary" class="truncate text-xs text-muted">
        <template v-if="mode === 'queue'">{{ item.status }} · {{ item.channel || "unknown" }}</template>
        <template v-else-if="mode === 'history'">{{ item.status }}</template>
        <template v-else-if="mode === 'search' && item.channel">{{ item.channel }}</template>
      </p>
      <p v-if="showDuration && item.duration_seconds != null" class="truncate text-xs text-muted">
        {{ formatDuration(item.duration_seconds) }}
      </p>
      <p v-if="item.uploaded_at" class="truncate text-xs text-muted">
        Uploaded {{ item.uploaded_at }}
      </p>
    </div>
    <div
      v-if="dropdownItems.length > 0"
      class="shrink-0 opacity-0 transition-opacity group-hover:opacity-100"
      @click.stop
    >
      <UDropdownMenu :items="dropdownItems" @update:open="(open) => !open && (playlistSearchTerm = '')">
        <template #playlist-filter>
          <div class="flex items-center gap-2 px-2 py-1.5">
            <UIcon name="i-lucide-search" class="size-4 shrink-0 text-muted" />
            <input
              v-model="playlistSearchTerm"
              type="text"
              placeholder="Find a playlist"
              class="min-w-0 flex-1 rounded-md border-0 bg-transparent px-2 py-1 text-sm placeholder-neutral-500 focus:outline-none focus:ring-0"
              @click.stop
              @keydown.stop
              @keyup.stop
              @keypress.stop
            />
          </div>
        </template>
        <UButton
          type="button"
          icon="i-lucide-more-horizontal"
          color="neutral"
          variant="ghost"
          size="xs"
          aria-label="More actions"
        />
      </UDropdownMenu>
    </div>
  </div>
  <UModal v-model:open="liveNameModalOpen" :ui="{ width: 'max-w-sm' }">
    <template #content>
      <form class="p-4" @submit.prevent="submitLiveName">
        <h3 class="text-lg font-semibold">Name this live stream</h3>
        <p class="mt-2 text-sm text-muted">
          A title is required before saving this live stream to a playlist.
        </p>
        <input
          v-model="liveNameInput"
          type="text"
          class="mt-3 w-full rounded-md border px-3 py-2 text-sm surface-input"
          placeholder="Stream name"
          @keydown.enter.prevent="submitLiveName"
        />
        <div class="mt-4 flex justify-end gap-2">
          <UButton type="button" color="neutral" variant="ghost" @click="liveNameModalOpen = false">
            Cancel
          </UButton>
          <UButton type="submit" color="primary" variant="solid">
            Save
          </UButton>
        </div>
      </form>
    </template>
  </UModal>
</template>

<script setup>
import { computed, ref } from "vue";

import { fetchJson } from "../composables/useApi";
import { formatDuration } from "../composables/useDuration";
import { useNotifications } from "../composables/useNotifications";

const playlistSearchTerm = ref("");
const liveNameModalOpen = ref(false);
const liveNameInput = ref("");
const pendingPlaylistId = ref(null);
const pendingPlaylistUrl = ref("");

const props = defineProps({
  item: {
    type: Object,
    required: true,
  },
  mode: {
    type: String,
    default: "search",
    validator: (v) => ["search", "queue", "history"].includes(v),
  },
  playlists: {
    type: Array,
    default: () => [],
  },
});

const { notifySuccess, notifyError } = useNotifications();

const thumbnailSrc = computed(() => {
  const item = props.item;
  if (item?.thumbnail_url) return item.thumbnail_url;
  const site = (item?.source_site || "").toString().toLowerCase();
  const videoId = item?.video_id ?? (site === "youtube" ? item?.id : null);
  if (site === "youtube" && videoId) return `https://i.ytimg.com/vi/${videoId}/hqdefault.jpg`;
  return "/static/placeholder-audio.svg";
});

const sourceSiteLabel = computed(() => props.item?.source_site || "");
const isLive = computed(() => Boolean(props.item?.is_live));

const showSecondary = computed(
  () => props.mode === "queue" || props.mode === "history" || props.mode === "search",
);
const showDuration = computed(() => props.item?.duration_seconds != null);

const filteredPlaylists = computed(() => {
  const term = playlistSearchTerm.value.toLowerCase().trim();
  if (!term) return props.playlists;
  return props.playlists.filter((p) => (p.title || "").toLowerCase().includes(term));
});

async function addToQueue(url) {
  if (!url) return;
  try {
    await fetchJson("/api/queue/add", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ url }),
    });
    notifySuccess("Added to queue", "URL added successfully.");
  } catch (error) {
    notifyError("Could not add URL", error);
  }
}

async function playNow(url) {
  if (!url) return;
  try {
    await fetchJson("/api/queue/play-now", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ url }),
    });
    notifySuccess("Playing now", "URL queued and playback started.");
  } catch (error) {
    notifyError("Could not play URL", error);
  }
}

async function addToPlaylist(playlistId, url) {
  if (!playlistId || !url) return;
  const requiresName = Boolean(isLive.value) && !(props.item?.title || "").trim();
  if (requiresName) {
    pendingPlaylistId.value = playlistId;
    pendingPlaylistUrl.value = url;
    liveNameInput.value = "";
    liveNameModalOpen.value = true;
    return;
  }
  await persistToPlaylist(playlistId, url, null);
}

async function persistToPlaylist(playlistId, url, customTitle) {
  try {
    await fetchJson(`/api/playlists/${playlistId}/entries`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ url, title: customTitle || props.item?.title || null }),
    });
    notifySuccess("Saved to playlist", "Item added to playlist.");
  } catch (error) {
    notifyError("Could not save to playlist", error);
  } finally {
    playlistSearchTerm.value = "";
  }
}

async function submitLiveName() {
  const title = (liveNameInput.value || "").trim();
  if (!title || !pendingPlaylistId.value || !pendingPlaylistUrl.value) return;
  await persistToPlaylist(pendingPlaylistId.value, pendingPlaylistUrl.value, title);
  liveNameModalOpen.value = false;
  pendingPlaylistId.value = null;
  pendingPlaylistUrl.value = "";
  liveNameInput.value = "";
}

const dropdownItems = computed(() => {
  const url = props.item?.source_url;
  const hasUrl = !!url;
  const items = [];

  if (hasUrl) {
    items.push([
      {
        label: "Play now",
        icon: "i-lucide-play",
        onSelect: () => playNow(url),
      },
    ]);
  }

  const addToPlaylistChildren = [
    { type: "label", slot: "playlist-filter" },
    ...filteredPlaylists.value.map((p) => ({
      label: p.title,
      onSelect: () => addToPlaylist(p.id, url),
    })),
  ];

  if (hasUrl && props.playlists.length > 0) {
    items.push([
      {
        label: "Add to playlist",
        icon: "i-lucide-plus",
        children: [addToPlaylistChildren],
      },
    ]);
  }

  if (hasUrl) {
    items.push([
      {
        label: "Add to queue",
        icon: "i-lucide-list-music",
        onSelect: () => addToQueue(url),
      },
    ]);
  }

  return items;
});
</script>
