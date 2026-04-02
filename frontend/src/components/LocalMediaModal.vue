<template>
  <UModal
    :open="open"
    :ui="{ width: 'w-full max-w-lg', content: 'rounded-xl surface-panel' }"
    @update:open="onOpenChange"
  >
    <template #content>
      <div class="p-4 flex flex-col gap-3 max-h-[min(80vh,32rem)]">
        <h2 class="text-lg font-semibold">Local media</h2>
        <p class="text-sm opacity-80">
          Browse allowed server folders or enter an absolute path. The server must list the directory in
          <code class="text-xs">AIRWAVE_LOCAL_MEDIA_ROOTS</code>.
        </p>
        <div v-if="errorMsg" class="text-sm text-red-400">
          {{ errorMsg }}
        </div>
        <div v-if="loading && !roots.length" class="text-sm opacity-70">
          Loading…
        </div>
        <div v-else-if="roots.length === 0" class="text-sm opacity-70">
          No media roots configured on the server.
        </div>
        <template v-else-if="browseView === 'pick_root'">
          <p class="text-sm font-medium">
            Choose a library folder
          </p>
          <ul class="flex flex-col gap-1 overflow-y-auto max-h-48">
            <li v-for="r in roots" :key="r.path">
              <UButton
                color="neutral"
                variant="ghost"
                class="w-full justify-start"
                :label="r.name || r.path"
                @click="enterRoot(r.path)"
              />
            </li>
          </ul>
        </template>
        <template v-else>
          <div class="flex items-center gap-2 min-w-0">
            <UButton
              color="neutral"
              variant="soft"
              size="sm"
              icon="i-bi-arrow-left"
              :disabled="!canGoUp"
              @click="goUp"
            />
            <span class="text-xs font-mono truncate shrink min-w-0" :title="currentDir">{{ currentDir }}</span>
          </div>
          <ul class="flex flex-col gap-1 overflow-y-auto min-h-[120px] max-h-[220px] border rounded-md border-neutral-600 p-1">
            <li v-for="e in entries" :key="e.path">
              <button
                type="button"
                class="w-full text-left px-2 py-1.5 rounded text-sm flex items-center gap-2 hover:bg-neutral-800"
                :class="selectedPath === e.path ? 'bg-neutral-800' : ''"
                @click="e.kind === 'directory' ? openDir(e.path) : selectFile(e.path)"
              >
                <UIcon
                  :name="e.kind === 'directory' ? 'i-bi-folder' : 'i-bi-file-earmark-music'"
                  class="size-4 shrink-0"
                />
                {{ e.name }}
              </button>
            </li>
          </ul>
          <div class="mt-3 flex flex-col gap-2 border-t border-neutral-600 pt-3">
            <p class="text-xs font-medium opacity-80">
              Folder: {{ currentDir }}
            </p>
            <label class="flex cursor-pointer items-center gap-2 text-sm">
              <input v-model="includeSubfolders" type="checkbox" class="rounded border-neutral-500">
              <span>Include subfolders</span>
            </label>
            <div class="flex flex-wrap gap-2">
              <UButton
                color="neutral"
                variant="soft"
                size="sm"
                @click="queueCurrentFolderAndClose"
              >
                Queue folder
              </UButton>
              <UButton
                color="neutral"
                variant="soft"
                size="sm"
                @click="playCurrentFolderAndClose"
              >
                Play folder
              </UButton>
              <UDropdownMenu
                v-if="localPlaylists.length"
                :items="playlistFolderMenuItemsForBrowse"
                :ui="{ separator: 'hidden' }"
                @update:open="(o) => !o && resetSearch()"
              >
                <template #playlist-filter>
                  <PlaylistSelectorFilter v-model="playlistSearchTerm" placeholder="Find a playlist" />
                </template>
                <UButton color="neutral" variant="soft" size="sm">
                  Save folder to playlist…
                </UButton>
              </UDropdownMenu>
            </div>
          </div>
        </template>
        <div>
          <label class="mb-1 block text-sm font-medium">Server path (manual)</label>
          <input
            v-model="manualPath"
            type="text"
            class="h-10 w-full rounded-md border px-3 text-sm font-mono surface-input"
            placeholder="/path/to/file or folder"
            @input="selectedPath = ''"
          >
        </div>
        <div
          v-if="manualPath.trim()"
          class="flex flex-col gap-2 border-t border-neutral-600 pt-3"
        >
          <p class="text-xs font-medium opacity-80">
            If the path above is a folder
          </p>
          <label class="flex cursor-pointer items-center gap-2 text-sm">
            <input v-model="includeSubfoldersManual" type="checkbox" class="rounded border-neutral-500">
            <span>Include subfolders</span>
          </label>
          <div class="flex flex-wrap gap-2">
            <UButton color="neutral" variant="soft" size="sm" @click="queueManualFolderAndClose">
              Queue folder
            </UButton>
            <UButton color="neutral" variant="soft" size="sm" @click="playManualFolderAndClose">
              Play folder
            </UButton>
            <UDropdownMenu
              v-if="localPlaylists.length"
              :items="playlistFolderMenuItemsManual"
              :ui="{ separator: 'hidden' }"
              @update:open="(o) => !o && resetSearch()"
            >
              <template #playlist-filter>
                <PlaylistSelectorFilter v-model="playlistSearchTerm" placeholder="Find a playlist" />
              </template>
              <UButton color="neutral" variant="soft" size="sm">
                Save folder to playlist…
              </UButton>
            </UDropdownMenu>
          </div>
        </div>
        <div class="flex flex-wrap gap-2">
          <UButton color="primary" variant="solid" :disabled="!effectivePath" @click="queueAndClose">
            Queue file
          </UButton>
          <UButton color="primary" variant="outline" :disabled="!effectivePath" @click="playAndClose">
            Play file
          </UButton>
          <UDropdownMenu
            v-if="localPlaylists.length"
            :items="playlistMenuItems"
            :ui="{ separator: 'hidden' }"
            @update:open="(o) => !o && resetSearch()"
          >
            <template #playlist-filter>
              <PlaylistSelectorFilter v-model="playlistSearchTerm" placeholder="Find a playlist" />
            </template>
            <UButton color="neutral" variant="soft" :disabled="!effectivePath">
              Save file to playlist…
            </UButton>
          </UDropdownMenu>
        </div>
      </div>
    </template>
  </UModal>
</template>

<script setup>
import { computed, ref, watch } from "vue";

import PlaylistSelectorFilter from "./PlaylistSelectorFilter.vue";
import { useLibraryState } from "../composables/useLibraryState";
import { usePlaylistSelector } from "../composables/usePlaylistSelector";

const props = defineProps({
  open: { type: Boolean, default: false },
});

const emit = defineEmits(["update:open"]);

const {
  playlists,
  fetchLocalRoots,
  browseLocalDirectory,
  addLocalPath,
  addLocalFolder,
  playLocalPath,
  playLocalFolder,
  addLocalPathToPlaylist,
  addLocalFolderToPlaylist,
} = useLibraryState();

const playlistSelector = usePlaylistSelector(playlists);
const { playlistSearchTerm, filteredPlaylists, resetSearch } = playlistSelector;

const localPlaylists = computed(() => (playlists.value ?? []).filter((p) => p?.kind !== "remote_youtube"));

const roots = ref([]);
const browseView = ref("pick_root");
const activeRoot = ref("");
const currentDir = ref("");
const entries = ref([]);
const selectedPath = ref("");
const manualPath = ref("");
const loading = ref(false);
const errorMsg = ref("");
const includeSubfolders = ref(true);
const includeSubfoldersManual = ref(true);

const effectivePath = computed(() => (manualPath.value.trim() || selectedPath.value).trim());

const canGoUp = computed(() => {
  if (browseView.value !== "browse") return false;
  if (!activeRoot.value || !currentDir.value) return false;
  if (roots.value.length > 1 && currentDir.value === activeRoot.value) return true;
  return currentDir.value !== activeRoot.value;
});

function dirParent(p) {
  const t = p.replace(/\/+$/, "");
  const i = t.lastIndexOf("/");
  if (i <= 0) return t;
  return t.slice(0, i) || "/";
}

function isUnderRoot(path, root) {
  return path === root || path.startsWith(root.endsWith("/") ? root : `${root}/`);
}

function onOpenChange(next) {
  emit("update:open", next);
}

function close() {
  emit("update:open", false);
}

async function bootstrap() {
  loading.value = true;
  errorMsg.value = "";
  try {
    const data = await fetchLocalRoots();
    roots.value = data.roots ?? [];
    if (roots.value.length === 1) {
      enterRoot(roots.value[0].path);
    } else {
      browseView.value = "pick_root";
    }
  } catch (e) {
    errorMsg.value = e?.message || "Could not load media roots";
    roots.value = [];
  } finally {
    loading.value = false;
  }
}

function enterRoot(path) {
  activeRoot.value = path;
  currentDir.value = path;
  browseView.value = "browse";
  selectedPath.value = "";
  loadBrowse();
}

function openDir(path) {
  currentDir.value = path;
  selectedPath.value = "";
  loadBrowse();
}

function selectFile(path) {
  selectedPath.value = path;
  manualPath.value = "";
}

function goUp() {
  if (currentDir.value === activeRoot.value) {
    if (roots.value.length > 1) browseView.value = "pick_root";
    return;
  }
  const parent = dirParent(currentDir.value);
  currentDir.value = isUnderRoot(parent, activeRoot.value) ? parent : activeRoot.value;
  loadBrowse();
}

async function loadBrowse() {
  loading.value = true;
  errorMsg.value = "";
  try {
    const data = await browseLocalDirectory(currentDir.value);
    entries.value = data.entries ?? [];
  } catch (e) {
    errorMsg.value = e?.message || "Browse failed";
    entries.value = [];
  } finally {
    loading.value = false;
  }
}

function queueAndClose() {
  const p = effectivePath.value;
  if (!p) return;
  addLocalPath(p);
  close();
}

function playAndClose() {
  const p = effectivePath.value;
  if (!p) return;
  playLocalPath(p);
  close();
}

function queueCurrentFolderAndClose() {
  if (!currentDir.value) return;
  addLocalFolder(currentDir.value, { recursive: includeSubfolders.value });
  close();
}

function playCurrentFolderAndClose() {
  if (!currentDir.value) return;
  playLocalFolder(currentDir.value, { recursive: includeSubfolders.value });
  close();
}

function queueManualFolderAndClose() {
  const p = manualPath.value.trim();
  if (!p) return;
  addLocalFolder(p, { recursive: includeSubfoldersManual.value });
  close();
}

function playManualFolderAndClose() {
  const p = manualPath.value.trim();
  if (!p) return;
  playLocalFolder(p, { recursive: includeSubfoldersManual.value });
  close();
}

const playlistMenuItems = computed(() => [
  [{ type: "label", slot: "playlist-filter" }],
  ...filteredPlaylists.value.map((p) => ({
    label: p.title,
    onSelect: () => {
      const path = (manualPath.value.trim() || selectedPath.value).trim();
      if (path) addLocalPathToPlaylist(p.id, path);
      close();
    },
  })),
]);

const playlistFolderMenuItemsForBrowse = computed(() => [
  [{ type: "label", slot: "playlist-filter" }],
  ...filteredPlaylists.value.map((p) => ({
    label: p.title,
    onSelect: () => {
      if (currentDir.value) {
        addLocalFolderToPlaylist(p.id, currentDir.value, { recursive: includeSubfolders.value });
      }
      close();
    },
  })),
]);

const playlistFolderMenuItemsManual = computed(() => [
  [{ type: "label", slot: "playlist-filter" }],
  ...filteredPlaylists.value.map((p) => ({
    label: p.title,
    onSelect: () => {
      const path = manualPath.value.trim();
      if (path) addLocalFolderToPlaylist(p.id, path, { recursive: includeSubfoldersManual.value });
      close();
    },
  })),
]);

watch(
  () => props.open,
  (isOpen) => {
    if (!isOpen) {
      manualPath.value = "";
      selectedPath.value = "";
      errorMsg.value = "";
      entries.value = [];
      includeSubfolders.value = true;
      includeSubfoldersManual.value = true;
      return;
    }
    bootstrap();
  },
);
</script>
