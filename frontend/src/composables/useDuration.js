export function formatDuration(value) {
  const totalSeconds = Math.max(0, Math.floor(Number(value) || 0));
  const hours = Math.floor(totalSeconds / 3600);
  const mins = String(Math.floor((totalSeconds % 3600) / 60)).padStart(2, "0");
  const secs = String(totalSeconds % 60).padStart(2, "0");

  if (hours > 0) {
    return `${String(hours).padStart(2, "0")}:${mins}:${secs}`;
  }

  return `${mins}:${secs}`;
}
