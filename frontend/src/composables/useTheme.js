import { ref } from "vue";

export const THEME_STORAGE_KEY = "airwave:settings:theme";
export const THEME_DARK = "dark";
export const THEME_NIGHT = "night";

const supportedThemes = [THEME_DARK, THEME_NIGHT];
const currentTheme = ref(THEME_DARK);

function readStoredTheme() {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(THEME_STORAGE_KEY);
  } catch {
    return null;
  }
}

function writeStoredTheme(theme) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // Ignore localStorage write errors and keep in-memory state.
  }
}

function applyThemeToDom(theme) {
  if (typeof document === "undefined") return;
  document.documentElement.setAttribute("data-theme", theme);
}

export function initializeTheme() {
  const storedTheme = readStoredTheme();
  const theme = supportedThemes.includes(storedTheme) ? storedTheme : THEME_DARK;
  currentTheme.value = theme;
  applyThemeToDom(theme);
  if (!storedTheme) {
    writeStoredTheme(THEME_DARK);
  }
}

export function useTheme() {
  function setTheme(theme) {
    if (!supportedThemes.includes(theme)) return;
    currentTheme.value = theme;
    applyThemeToDom(theme);
    writeStoredTheme(theme);
  }

  return {
    currentTheme,
    supportedThemes,
    setTheme,
  };
}
