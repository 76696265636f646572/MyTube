<template>
  <header class="rounded-xl border border-neutral-700 bg-neutral-900 p-3">
    <div class="flex flex-col gap-2 sm:flex-row sm:items-center">
      <h1 class="text-2xl font-bold leading-tight">MyTube Radio</h1>
      <div class="flex w-full flex-col gap-2 sm:ml-auto sm:w-auto sm:flex-row sm:flex-wrap sm:justify-end">
        <input
          :value="searchText"
          type="search"
          placeholder="Search local + YouTube"
          class="h-10 w-full min-w-0 rounded-md border border-neutral-700 bg-neutral-800 px-3 text-sm sm:w-[320px]"
          @input="$emit('search-text-change', $event.target.value)"
          @keydown.enter.prevent="$emit('search', searchText)"
        />
        <UButton
          type="button"
          color="primary"
          variant="solid"
          size="md"
          class="self-start sm:self-auto"
          @click="$emit('search', searchText)"
        >
          Search
        </UButton>
      </div>
    </div>

    <form class="mt-3 flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center" @submit.prevent="emitAddUrl">
      <input
        v-model="urlInput"
        type="url"
        placeholder="https://www.youtube.com/watch?v=..."
        required
        class="h-10 w-full min-w-0 flex-1 rounded-md border border-neutral-700 bg-neutral-800 px-3 text-sm"
      />
      <div class="flex w-full gap-2 sm:w-auto">
      <UButton type="submit" color="primary" variant="solid" size="md" class="flex-1 sm:flex-none">
        Add URL
      </UButton>
      <UButton type="button" color="neutral" variant="outline" size="md" class="flex-1 sm:flex-none" @click="emitPlayUrl">
        Play URL
      </UButton>
      </div>
    </form>

  </header>
</template>

<script setup>
import { ref } from "vue";

defineProps({
  searchText: {
    type: String,
    default: "",
  },
});

const emit = defineEmits(["add-url", "play-url", "search", "search-text-change"]);
const urlInput = ref("");

function emitAddUrl() {
  const url = urlInput.value.trim();
  if (!url) return;
  emit("add-url", url);
  urlInput.value = "";
}

function emitPlayUrl() {
  const url = urlInput.value.trim();
  if (!url) return;
  emit("play-url", url);
  urlInput.value = "";
}
</script>
