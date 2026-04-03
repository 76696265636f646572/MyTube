<template>
  <UDropdownMenu
    :items="dropdownItems"
    :ui="{ separator: 'hidden' }"
    @update:open="(open) => !open && resetSearch()"
  >
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
</template>

<script setup>
import { computed } from "vue";

import PlaylistSelectorFilter from "../PlaylistSelectorFilter.vue";
import { usePlaylistSelector } from "../../composables/usePlaylistSelector";

const props = defineProps({
  entry: {
    type: Object,
    required: true,
  },
  playlists: {
    type: Array,
    default: () => [],
  },
});

const emit = defineEmits(["queue", "play", "add-to-playlist"]);

const { playlistSearchTerm, filteredPlaylists, resetSearch } = usePlaylistSelector(() => props.playlists);

const dropdownItems = computed(() => {
  const items = [
    {
      label: "Queue",
      icon: "i-bi-music-note-list",
      onSelect: () => emit("queue"),
    },
    {
      label: "Play now",
      icon: "i-bi-play-fill",
      onSelect: () => emit("play"),
    },
  ];

  if (props.playlists.length > 0) {
    const addToPlaylistChildren = [
      { type: "label", slot: "playlist-filter" },
      ...filteredPlaylists.value.map((p) => ({
        label: p.title,
        onSelect: () => emit("add-to-playlist", p.id),
      })),
    ];
    items.push({
      label: "Add to playlist",
      icon: "i-bi-plus",
      children: [addToPlaylistChildren],
    });
  }

  return items;
});
</script>
