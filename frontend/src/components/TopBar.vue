<template>
  <header class="rounded-xl border border-neutral-700 bg-neutral-900 p-3">
    <div class="flex flex-wrap items-center gap-2">
      <h1 class="text-2xl font-bold">MyTube Radio</h1>
      <div class="ml-auto flex flex-wrap gap-2">
        <input
          :value="searchText"
          type="search"
          placeholder="Search local + YouTube"
          class="h-10 w-[320px] max-w-full rounded-md border border-neutral-700 bg-neutral-800 px-3 text-sm"
          @input="$emit('search-text-change', $event.target.value)"
          @keydown.enter.prevent="$emit('search', searchText)"
        />
        <button
          type="button"
          class="h-10 rounded-md border border-neutral-700 bg-neutral-800 px-3 text-sm hover:bg-neutral-700"
          @click="$emit('search', searchText)"
        >
          Search
        </button>
      </div>
    </div>

    <form class="mt-3 flex flex-wrap items-center gap-2" @submit.prevent="emitAddUrl">
      <input
        v-model="urlInput"
        type="url"
        placeholder="https://www.youtube.com/watch?v=..."
        required
        class="h-10 min-w-[220px] flex-1 rounded-md border border-neutral-700 bg-neutral-800 px-3 text-sm"
      />
      <button type="submit" class="h-10 rounded-md border border-neutral-700 bg-neutral-800 px-3 text-sm hover:bg-neutral-700">
        Add URL
      </button>
      <button
        type="button"
        class="h-10 rounded-md border border-neutral-700 bg-neutral-900 px-3 text-sm hover:bg-neutral-800"
        @click="emitPlayUrl"
      >
        Play URL
      </button>
    </form>

    <div v-if="searchResults.length" class="mt-3">
      <h2 class="mb-2 text-base font-semibold">YouTube Results</h2>
      <ul class="space-y-1">
        <li
          v-for="item in searchResults"
          :key="item.id"
          class="flex flex-wrap items-center gap-2 rounded-md border border-neutral-700 px-2 py-2"
        >
          <span class="min-w-0 flex-1 truncate text-sm">{{ item.title || item.source_url }}</span>
          <button
            type="button"
            class="rounded-md border border-neutral-700 bg-neutral-800 px-2 py-1 text-xs hover:bg-neutral-700"
            @click="$emit('add-url', item.source_url)"
          >
            Add
          </button>
          <button
            type="button"
            class="rounded-md border border-neutral-700 bg-neutral-900 px-2 py-1 text-xs hover:bg-neutral-800"
            @click="$emit('play-url', item.source_url)"
          >
            Play
          </button>
        </li>
      </ul>
    </div>
  </header>
</template>

<script setup>
import { ref } from "vue";

defineProps({
  searchText: {
    type: String,
    default: "",
  },
  searchResults: {
    type: Array,
    default: () => [],
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
