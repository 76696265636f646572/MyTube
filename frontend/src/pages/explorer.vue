<template>
  <section class="min-h-0 min-w-0 overflow-auto rounded-xl border border-neutral-700 p-4 md:p-6 surface-panel">
    <div class="mb-5 flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="text-2xl font-bold tracking-tight md:text-3xl">Media Browser</h1>
        <p class="mt-1 text-sm text-muted">
          Browse allowed server folders and queue local files or folders.
        </p>
      </div>
      <label class="inline-flex cursor-pointer items-center gap-2 text-sm">
        <input v-model="includeSubfolders" type="checkbox" class="rounded border-neutral-500">
        <span>Include subfolders</span>
      </label>
    </div>

    <div class="mb-4 flex flex-wrap items-center gap-2">
      <UButton
        color="neutral"
        variant="soft"
        size="sm"
        icon="i-bi-house"
        :disabled="!currentDir"
        @click="showRoots"
      >
        Roots
      </UButton>
      <UButton
        color="neutral"
        variant="soft"
        size="sm"
        icon="i-bi-arrow-up"
        :disabled="!canGoUp"
        @click="goUp"
      >
        Up
      </UButton>
      <div v-if="breadcrumbs.length" class="min-w-0 flex-1 overflow-x-auto">
        <nav class="flex min-w-max items-center gap-1 text-sm">
          <template v-for="(crumb, idx) in breadcrumbs" :key="crumb.path">
            <button
              type="button"
              class="rounded px-1.5 py-1 hover:bg-neutral-800"
              @click="openBreadcrumb(crumb.path)"
            >
              {{ crumb.label }}
            </button>
            <span v-if="idx < breadcrumbs.length - 1" class="text-muted">/</span>
          </template>
        </nav>
      </div>
    </div>

    <div v-if="errorMsg" class="mb-3 text-sm text-red-400">
      {{ errorMsg }}
    </div>
    <div v-if="loading" class="text-sm opacity-70">
      Loading…
    </div>
    <div v-else-if="showingRoots && roots.length === 0" class="text-sm opacity-70">
      No media roots configured on the server.
    </div>
    <div v-else>
      <ul class="space-y-2 md:grid md:grid-cols-3 md:gap-3 md:space-y-0 lg:grid-cols-4 xl:grid-cols-5">
        <li v-for="entry in visibleEntries" :key="entry.path" class="min-w-0">
          <ExplorerFolder
            v-if="entry.kind === 'directory'"
            :entry="entry"
            :playlists="localPlaylists"
            :show-path="showingRoots"
            @open="openDirectory(entry.path)"
            @queue="queueFolder(entry.path)"
            @play="playFolder(entry.path)"
            @add-to-playlist="(playlistId) => addFolderToPlaylist(playlistId, entry.path)"
          />
          <ExplorerFile
            v-else
            :entry="entry"
            :playlists="localPlaylists"
            @queue="queueFile(entry.path)"
            @play="playFile(entry.path)"
            @add-to-playlist="(playlistId) => addFileToPlaylist(playlistId, entry.path)"
          />
        </li>
      </ul>
      <div v-if="!visibleEntries.length" class="py-8 text-center text-sm text-muted">
        No files or folders found here.
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";

import ExplorerFile from "../components/explorer/ExplorerFile.vue";
import ExplorerFolder from "../components/explorer/ExplorerFolder.vue";
import { useLibraryState } from "../composables/useLibraryState";

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

const roots = ref([]);
const currentDir = ref("");
const activeRoot = ref("");
const entries = ref([]);
const loading = ref(false);
const errorMsg = ref("");
const includeSubfolders = ref(true);

const localPlaylists = computed(() => (playlists.value ?? []).filter((p) => p?.kind !== "remote_youtube"));
const showingRoots = computed(() => !currentDir.value);
function compareEntries(a, b) {
  const aIsDirectory = a?.kind === "directory";
  const bIsDirectory = b?.kind === "directory";
  if (aIsDirectory !== bIsDirectory) return aIsDirectory ? -1 : 1;
  const aName = (a?.name || "").toString();
  const bName = (b?.name || "").toString();
  return aName.localeCompare(bName, undefined, { sensitivity: "base", numeric: true });
}

const visibleEntries = computed(() => {
  if (showingRoots.value) {
    return roots.value.map((root) => ({
      kind: "directory",
      path: root.path,
      name: root.name || pathLabel(root.path),
    })).sort(compareEntries);
  }
  return [...entries.value].sort(compareEntries);
});

const canGoUp = computed(() => {
  if (showingRoots.value) return false;
  if (!activeRoot.value || !currentDir.value) return false;
  return currentDir.value !== activeRoot.value;
});

const breadcrumbs = computed(() => {
  if (!currentDir.value || !activeRoot.value) return [];
  const root = roots.value.find((r) => r.path === activeRoot.value);
  const rootLabel = root?.name || pathLabel(activeRoot.value);
  const crumbs = [{ path: activeRoot.value, label: rootLabel }];

  if (currentDir.value === activeRoot.value) return crumbs;

  const normalizedRoot = activeRoot.value.endsWith("/") ? activeRoot.value : `${activeRoot.value}/`;
  const relative = currentDir.value.startsWith(normalizedRoot) ? currentDir.value.slice(normalizedRoot.length) : "";
  if (!relative) return crumbs;

  const segments = relative.split("/").filter(Boolean);
  let currentPath = activeRoot.value;
  for (const segment of segments) {
    currentPath = `${currentPath.replace(/\/+$/, "")}/${segment}`;
    crumbs.push({ path: currentPath, label: segment });
  }
  return crumbs;
});

function pathLabel(path) {
  if (!path) return "/";
  const trimmed = path.replace(/\/+$/, "");
  const parts = trimmed.split("/").filter(Boolean);
  return parts[parts.length - 1] || "/";
}

function dirParent(path) {
  const trimmed = path.replace(/\/+$/, "");
  const index = trimmed.lastIndexOf("/");
  if (index <= 0) return trimmed;
  return trimmed.slice(0, index) || "/";
}

function isUnderRoot(path, root) {
  return path === root || path.startsWith(root.endsWith("/") ? root : `${root}/`);
}

async function loadRoots() {
  loading.value = true;
  errorMsg.value = "";
  try {
    const data = await fetchLocalRoots();
    roots.value = data.roots ?? [];
  } catch (error) {
    errorMsg.value = error?.message || "Could not load media roots";
    roots.value = [];
  } finally {
    loading.value = false;
  }
}

async function loadDirectory(path) {
  loading.value = true;
  errorMsg.value = "";
  try {
    const data = await browseLocalDirectory(path);
    entries.value = data.entries ?? [];
  } catch (error) {
    errorMsg.value = error?.message || "Browse failed";
    entries.value = [];
  } finally {
    loading.value = false;
  }
}

async function openDirectory(path) {
  if (!path) return;
  if (!activeRoot.value || path === activeRoot.value || roots.value.some((root) => root.path === path)) {
    activeRoot.value = roots.value.some((root) => root.path === path) ? path : activeRoot.value;
  }
  currentDir.value = path;
  await loadDirectory(path);
}

function showRoots() {
  currentDir.value = "";
  activeRoot.value = "";
  entries.value = [];
}

async function openBreadcrumb(path) {
  if (!path) return;
  await openDirectory(path);
}

async function goUp() {
  if (!canGoUp.value) return;
  const parent = dirParent(currentDir.value);
  const nextPath = isUnderRoot(parent, activeRoot.value) ? parent : activeRoot.value;
  await openDirectory(nextPath);
}

function queueFile(path) {
  addLocalPath(path);
}

function playFile(path) {
  playLocalPath(path);
}

function queueFolder(path) {
  addLocalFolder(path, { recursive: includeSubfolders.value });
}

function playFolder(path) {
  playLocalFolder(path, { recursive: includeSubfolders.value });
}

function addFileToPlaylist(playlistId, path) {
  addLocalPathToPlaylist(playlistId, path);
}

function addFolderToPlaylist(playlistId, path) {
  addLocalFolderToPlaylist(playlistId, path, { recursive: includeSubfolders.value });
}

onMounted(() => {
  loadRoots();
});
</script>
