const notificationStore = {
  toast: null,
};

export function formatErrorMessage(error) {
  const fallback = error instanceof Error ? error.message : String(error || "Request failed");
  try {
    const parsed = JSON.parse(fallback);
    if (Array.isArray(parsed?.detail) && parsed.detail.length) {
      return parsed.detail[0]?.msg || fallback;
    }
    if (typeof parsed?.detail === "string") {
      return parsed.detail;
    }
  } catch {
    // Keep the original message when the payload is not JSON.
  }
  return fallback.length > 180 ? `${fallback.slice(0, 177)}...` : fallback;
}

export function initializeNotifications(toast) {
  notificationStore.toast = toast;
}

export function useNotifications() {
  function notifySuccess(title, description) {
    notificationStore.toast?.add({
      title,
      description,
      color: "success",
      icon: "i-lucide-check",
      type: "foreground",
    });
  }

  function notifyError(title, error) {
    notificationStore.toast?.add({
      title,
      description: formatErrorMessage(error),
      color: "error",
      icon: "i-lucide-triangle-alert",
      type: "foreground",
    });
  }

  return { notifySuccess, notifyError };
}
