<template>
  <div class="group flex min-w-0 items-center gap-3 rounded-md border px-3 py-2 playlist-card">
    
    <div
      v-if="thumbnailSrc"
      class="relative h-14 w-24 shrink-0 overflow-hidden rounded surface-elevated"
      @click="playNow(item.source_url)"
    >
      <img
        :src="thumbnailSrc"
        :alt="item.title || 'Thumbnail'"
        class="h-full w-full object-cover"
        loading="lazy"
        referrerpolicy="no-referrer"
      />
      <div
        class="absolute inset-0 flex cursor-pointer items-center justify-center bg-black/40 opacity-100 transition-opacity md:opacity-0 md:group-hover:opacity-100"
        aria-hidden
      >
        <UIcon name="i-bi-play-fill" class="size-8 text-white drop-shadow-md" />
      </div>
    </div>
    
    <div class="min-w-0 flex-1">
      <p class="truncate text-sm font-medium">
        <template v-if="mode === 'queue' && item.queue_position != null">#{{ item.queue_position }} </template>
        {{ item.title || item.source_url }}
      </p>
      <p v-if="item.provider" class="truncate text-xs text-muted">
        <UBadge :label="providerLabel" color="neutral" variant="soft" class="shrink-0" />
      </p>
      <p v-if="showSecondary" class="truncate text-xs text-muted">
        <template v-if="mode === 'queue'">{{ item.status }} · {{ item.channel || "unknown" }}</template>
        <template v-else-if="mode === 'history'">{{ item.status }}</template>
        <template v-else-if="mode === 'search' && item.channel">{{ item.channel }}</template>
      </p>
      <p v-if="item.duration_seconds != null" class="truncate text-xs text-muted">
        {{ formatDuration(item.duration_seconds) }}
      </p>
    </div>
    <div
      v-if="dropdownItems.length > 0"
      class="shrink-0 opacity-100 transition-opacity md:opacity-0 md:group-hover:opacity-100"
      @click.stop
    >
      <UDropdownMenu :items="dropdownItems" :ui="{ separator: 'hidden' }" @update:open="(open) => !open && resetSearch()">
        <template #playlist-filter>
          <PlaylistSelectorFilter v-model="playlistSearchTerm" placeholder="Find a playlist" />
        </template>
        <UButton
          class="cursor-pointer"
          type="button"
          icon="i-bi-three-dots"
          color="neutral"
          variant="ghost"
          size="xs"
          aria-label="More actions"
        />
      </UDropdownMenu>
    </div>
  </div>
</template>

<script setup>
import { computed } from "vue";

import PlaylistSelectorFilter from "./PlaylistSelectorFilter.vue";
import { fetchJson } from "../composables/useApi";
import { formatDuration } from "../composables/useDuration";
import { useNotifications } from "../composables/useNotifications";
import { usePlaylistSelector } from "../composables/usePlaylistSelector";

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
  playlistId: {
    type: String,
    default: null,
  },
  entryId: {
    type: Number,
    default: null,
  },
});

const emit = defineEmits(["deleted"]);

const { playlistSearchTerm, filteredPlaylists, resetSearch } = usePlaylistSelector(() => props.playlists);
const { notifySuccess, notifyError } = useNotifications();

const thumbnailSrc = computed(() => {
  const item = props.item;
  if (item?.thumbnail_url) return item.thumbnail_url;
  if (item?.provider === "youtube" && item?.provider_item_id) {
    return `https://i.ytimg.com/vi/${item.provider_item_id}/hqdefault.jpg`;
  }
  return "";
});

const showSecondary = computed(
  () => props.mode === "queue" || props.mode === "history" || (props.mode === "search" && props.item?.channel),
);

const providerLabel = computed(() => {
  const item = props.item;
  if (item?.provider) {
    return item.provider.charAt(0).toUpperCase() + item.provider.slice(1);
  }
  return "";
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
  try {
    await fetchJson(`/api/playlists/${playlistId}/entries`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ url }),
    });
    notifySuccess("Saved to playlist", "Item added to playlist.");
  } catch (error) {
    notifyError("Could not save to playlist", error);
  } finally {
    resetSearch();
  }
}

async function removeFromPlaylist(entryId) {
  if (!entryId) return;
  try {
    const response = await fetch(`/api/playlists/entries/${entryId}`, {
      method: "DELETE",
    });
    if (!response.ok) {
      const detail = await response.text();
      throw new Error(detail || `Request failed: ${response.status}`);
    }
    notifySuccess("Removed from playlist", "Item removed.");
    emit("deleted");
  } catch (error) {
    notifyError("Could not remove from playlist", error);
  }
}

const dropdownItems = computed(() => {
  const url = props.item?.source_url;
  const hasUrl = !!url;
  const items = [];

  if (hasUrl) {
    items.push(
      {
        label: "Play now",
        icon: "i-bi-play-fill",
        onSelect: () => playNow(url),
      },
    );
  }
  if (hasUrl) {
    items.push(
      {
        label: "Add to queue",
        icon: "i-bi-music-note-list",
        onSelect: () => addToQueue(url),
      },
    );
  }
  const addToPlaylistChildren = [
    { type: "label", slot: "playlist-filter" },
    ...filteredPlaylists.value.map((p) => ({
      label: p.title,
      onSelect: () => addToPlaylist(p.id, url),
    })),
  ];

  if (hasUrl && props.playlists.length > 0) {
    items.push(
      {
        label: "Add to playlist",
        icon: "i-bi-plus",
        children: [addToPlaylistChildren],
      },
    );
  }

 

  if (props.playlistId && props.entryId != null) {
    items.push(
      {
        label: "Remove from playlist",
        icon: "i-bi-trash-fill",
        onSelect: () => removeFromPlaylist(props.entryId),
      },
    );
  }
  return items;
});
</script>
