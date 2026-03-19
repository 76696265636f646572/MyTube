import { ref } from "vue";

const open = ref(false);
const targetPlaylistTitle = ref("");
const pendingAddAll = ref(null);
const pendingAddNewOnes = ref(null);

export function useDuplicateModal() {
  function showDuplicateModal({ targetPlaylistTitle: title, onAddAll, onAddNewOnes }) {
    targetPlaylistTitle.value = title || "Untitled playlist";
    pendingAddAll.value = onAddAll;
    pendingAddNewOnes.value = onAddNewOnes;
    open.value = true;
  }

  function close() {
    open.value = false;
    pendingAddAll.value = null;
    pendingAddNewOnes.value = null;
  }

  async function handleAddAll() {
    const fn = pendingAddAll.value;
    close();
    if (typeof fn === "function") await fn();
  }

  async function handleAddNewOnes() {
    const fn = pendingAddNewOnes.value;
    close();
    if (typeof fn === "function") await fn();
  }

  return {
    open,
    targetPlaylistTitle,
    showDuplicateModal,
    close,
    handleAddAll,
    handleAddNewOnes,
  };
}
