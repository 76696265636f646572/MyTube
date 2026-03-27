<template>
  <li
    class="group flex items-start gap-2 rounded-md border p-2 cursor-pointer transition-colors playlist-card"
    :class="isActive ? 'bg-primary-500/20' : 'hover:bg-neutral-700/50'"
    @click="$emit('click', playlist)"
  >
    <div
      class="min-w-0 flex-1 flex items-center gap-2 rounded py-1.5 -m-1"
      :class="isActive ? 'text-primary-400' : ''"
    >
      <img
        v-if="thumbnailSrc"
        :src="thumbnailSrc"
        alt=""
        class="h-10 w-10 shrink-0 rounded object-cover"
      />
      <div class="min-w-0 text-left">
        <span class="flex items-center gap-1 text-sm font-medium">
          <span class="truncate">{{ playlist.title }}</span>
          <UIcon
            v-if="playlist.pinned"
            name="i-bi-pin-fill"
            class="size-3 shrink-0 text-muted"
            aria-hidden="true"
          />
        </span>
        <span class="block text-xs text-muted">{{ label }} · {{ playlist.entry_count }}</span>
      </div>
    </div>
    <div class="shrink-0 opacity-100 transition-opacity md:opacity-0 md:group-hover:opacity-100" @click.stop>
      <UDropdownMenu :items="dropdownItems" :ui="{ separator: 'hidden' }">
        <UButton
          type="button"
          icon="i-bi-three-dots"
          color="neutral"
          variant="ghost"
          size="xs"
          aria-label="More actions"
          class="cursor-pointer"
        />
      </UDropdownMenu>
    </div>
  </li>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  playlist: {
    type: Object,
    required: true,
  },
  activePlaylistId: {
    type: Number,
    default: null,
  },
  isRemotePlaylist: {
    type: Function,
    required: true,
  },
  dropdownItems: {
    type: Array,
    default: () => [],
  },
  thumbnailSrc: {
    type: String,
    default: "",
  },
  label: {
    type: String,
    default: "",
  },
});

defineEmits(["click"]);

const isActive = computed(() => props.playlist.id === props.activePlaylistId && !props.isRemotePlaylist(props.playlist));
</script>
