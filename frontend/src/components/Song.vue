<template>
  <div class="group flex items-center gap-3 rounded-md border border-neutral-700 px-3 py-2">
    <img
      v-if="thumbnailSrc"
      :src="thumbnailSrc"
      :alt="item.title || 'Thumbnail'"
      class="h-14 w-24 shrink-0 rounded object-cover bg-neutral-800"
      loading="lazy"
      referrerpolicy="no-referrer"
    />
    <div class="min-w-0 flex-1">
      <p class="truncate text-sm font-medium">
        <template v-if="mode === 'queue' && item.queue_position != null">#{{ item.queue_position }} </template>
        {{ item.title || item.source_url }}
      </p>
      <p v-if="showSecondary" class="truncate text-xs text-neutral-400">
        <template v-if="mode === 'queue'">{{ item.status }} · {{ item.channel || "unknown" }}</template>
        <template v-else-if="mode === 'history'">{{ item.status }}</template>
        <template v-else-if="mode === 'search' && item.channel">{{ item.channel }}</template>
      </p>
      <p v-if="showDuration && item.duration_seconds != null" class="truncate text-xs text-neutral-400">
        {{ formatDuration(item.duration_seconds) }}
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
            <UIcon name="i-lucide-search" class="size-4 shrink-0 text-neutral-400" />
            <input
              v-model="playlistSearchTerm"
              type="text"
              placeholder="Find a playlist"
              class="min-w-0 flex-1 rounded-md border-0 bg-transparent px-2 py-1 text-sm text-neutral-100 placeholder-neutral-500 focus:outline-none focus:ring-0"
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
</template>

<script setup>
import { computed, ref } from "vue";

import { formatDuration } from "../composables/useDuration";

const playlistSearchTerm = ref("");

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
  onAddToPlaylist: {
    type: Function,
    default: null,
  },
  onAddToQueue: {
    type: Function,
    default: null,
  },
});

const thumbnailSrc = computed(() => {
  const item = props.item;
  if (item?.thumbnail_url) return item.thumbnail_url;
  if (item?.id) return `https://i.ytimg.com/vi/${item.id}/hqdefault.jpg`;
  return "";
});

const showSecondary = computed(
  () => props.mode === "queue" || props.mode === "history" || (props.mode === "search" && props.item?.channel),
);
const showDuration = computed(() => props.mode === "search");

const filteredPlaylists = computed(() => {
  const term = playlistSearchTerm.value.toLowerCase().trim();
  if (!term) return props.playlists;
  return props.playlists.filter((p) => (p.title || "").toLowerCase().includes(term));
});

const dropdownItems = computed(() => {
  const url = props.item?.source_url;
  const hasUrl = !!url;
  const items = [];

  const addToPlaylistChildren = [
    { type: "label", slot: "playlist-filter" },
    ...filteredPlaylists.value.map((p) => ({
      label: p.title,
      onSelect: () => {
        if (props.onAddToPlaylist) props.onAddToPlaylist(p.id, url);
        playlistSearchTerm.value = "";
      },
    })),
  ];

  if (hasUrl && props.onAddToPlaylist && props.playlists.length > 0) {
    items.push([
      {
        label: "Add to playlist",
        icon: "i-lucide-plus",
        children: [addToPlaylistChildren],
      },
    ]);
  }

  if (hasUrl && props.onAddToQueue) {
    items.push([
      {
        label: "Add to queue",
        icon: "i-lucide-list-music",
        onSelect: () => props.onAddToQueue(url),
      },
    ]);
  }

  return items;
});
</script>
