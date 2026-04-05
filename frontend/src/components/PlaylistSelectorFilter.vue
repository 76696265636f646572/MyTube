<template>
  <div class="flex flex-col gap-2 px-2 py-1.5">
    <div class="flex items-center gap-2">
      <UIcon name="i-bi-search" class="size-4 shrink-0 text-muted" />
      <input
        :value="modelValue"
        type="text"
        class="min-w-0 flex-1 border-0 bg-transparent px-2 py-1 text-sm placeholder:text-neutral-500 focus:outline-none focus:ring-0"
        :placeholder="placeholder"
        @input="emit('update:modelValue', $event.target.value)"
        @click.stop
        @keydown.stop
        @keyup.stop
        @keypress.stop
      />
    </div>
    <form
      v-if="showCreate"
      class="flex items-center gap-2 border-t border-neutral-600/60 pt-2"
      @submit.prevent="submitCreate"
    >
      <UIcon name="i-bi-plus-lg" class="size-4 shrink-0 text-muted" aria-hidden="true" />
      <input
        v-model="newTitle"
        type="text"
        :placeholder="createPlaceholder"
        class="min-w-0 flex-1 rounded-md border-0 bg-transparent px-2 py-1 text-sm placeholder-neutral-500 focus:outline-none focus:ring-0"
        :disabled="creating"
        @click.stop
        @keydown.stop
        @keyup.stop
        @keypress.stop
      />
      <UButton
        type="submit"
        size="xs"
        color="primary"
        variant="soft"
        class="shrink-0"
        :disabled="creating || !newTitle.trim()"
        @click.stop
      >
        Create
      </UButton>
    </form>
  </div>
</template>

<script setup>
import { ref } from "vue";

import { useLibraryState } from "../composables/useLibraryState";

const props = defineProps({
  modelValue: {
    type: String,
    default: "",
  },
  placeholder: {
    type: String,
    default: "Find a playlist",
  },
  showCreate: {
    type: Boolean,
    default: true,
  },
  createPlaceholder: {
    type: String,
    default: "New playlist name",
  },
});

const emit = defineEmits(["update:modelValue", "playlist-created"]);

const { createPlaylist } = useLibraryState();
const newTitle = ref("");
const creating = ref(false);

async function submitCreate() {
  const title = newTitle.value.trim();
  if (!title || creating.value) return;
  creating.value = true;
  try {
    const created = await createPlaylist(title);
    if (created?.id) {
      newTitle.value = "";
      emit("playlist-created", created);
    }
  } finally {
    creating.value = false;
  }
}
</script>
