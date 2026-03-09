const addUrlForm = document.getElementById("add-url-form");
const urlInput = document.getElementById("url-input");
const queueList = document.getElementById("queue-list");
const historyList = document.getElementById("history-list");
const stateText = document.getElementById("state-text");
const skipBtn = document.getElementById("skip-btn");
const sonosList = document.getElementById("sonos-list");
const refreshSonosBtn = document.getElementById("refresh-sonos-btn");

async function fetchJson(url, options = {}) {
  const resp = await fetch(url, options);
  if (!resp.ok) {
    const detail = await resp.text();
    throw new Error(detail || `Request failed: ${resp.status}`);
  }
  return await resp.json();
}

function renderQueue(items) {
  queueList.innerHTML = "";
  for (const item of items) {
    const li = document.createElement("li");
    li.textContent = `#${item.queue_position} ${item.title || item.source_url} [${item.status}]`;
    const remove = document.createElement("button");
    remove.textContent = "Remove";
    remove.addEventListener("click", async () => {
      await fetch(`/api/queue/${item.id}`, { method: "DELETE" });
      await refreshAll();
    });
    li.appendChild(remove);
    queueList.appendChild(li);
  }
}

function renderHistory(items) {
  historyList.innerHTML = "";
  for (const item of items) {
    const li = document.createElement("li");
    li.textContent = `${item.title || item.source_url} -> ${item.status}`;
    historyList.appendChild(li);
  }
}

function renderState(state) {
  stateText.textContent = `${state.mode.toUpperCase()} | ${state.now_playing_title || "No active track"}`;
}

async function refreshSonos() {
  const speakers = await fetchJson("/api/sonos/speakers");
  sonosList.innerHTML = "";
  for (const speaker of speakers) {
    const li = document.createElement("li");
    const btn = document.createElement("button");
    btn.textContent = `Play on ${speaker.name}`;
    btn.addEventListener("click", async () => {
      await fetchJson("/api/sonos/play", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ speaker_ip: speaker.ip }),
      });
    });
    li.textContent = `${speaker.name} (${speaker.ip}) `;
    li.appendChild(btn);
    sonosList.appendChild(li);
  }
}

async function refreshAll() {
  const [queue, history, state] = await Promise.all([
    fetchJson("/api/queue"),
    fetchJson("/api/history"),
    fetchJson("/api/state"),
  ]);
  renderQueue(queue);
  renderHistory(history);
  renderState(state);
}

addUrlForm.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const url = urlInput.value.trim();
  if (!url) return;
  await fetchJson("/api/queue/add", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ url }),
  });
  urlInput.value = "";
  await refreshAll();
});

skipBtn.addEventListener("click", async () => {
  await fetchJson("/api/queue/skip", { method: "POST" });
  await refreshAll();
});

refreshSonosBtn.addEventListener("click", refreshSonos);

refreshAll();
setInterval(refreshAll, 3000);
