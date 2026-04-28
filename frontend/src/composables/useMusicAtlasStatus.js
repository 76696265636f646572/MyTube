import { ref } from "vue";

import { fetchJson } from "./useApi";

const musicAtlasEnabled = ref(false);
const musicAtlasStatusLoaded = ref(false);
let loadPromise = null;

export async function ensureMusicAtlasStatusLoaded() {
  if (musicAtlasStatusLoaded.value) return;
  if (loadPromise) {
    await loadPromise;
    return;
  }
  loadPromise = (async () => {
    try {
      const body = await fetchJson("/api/musicatlas/status");
      musicAtlasEnabled.value = !!body?.enabled;
      musicAtlasStatusLoaded.value = true;
    } catch {
      musicAtlasEnabled.value = false;
      musicAtlasStatusLoaded.value = false;
    } finally {
      loadPromise = null;
    }
  })();
  await loadPromise;
}

export function useMusicAtlasStatus() {
  return {
    musicAtlasEnabled,
    musicAtlasStatusLoaded,
    ensureMusicAtlasStatusLoaded,
  };
}
