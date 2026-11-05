// Логика попапа: потоки со страницы + очередь/история загрузок через локальный сервис
const SRV = "http://localhost:8765";

const el = (id) => document.getElementById(id);
const nameInput = el("name");
const streamsWrap = el("streamsWrap"), streamsSel = el("streams");
const streamCount = el("streamCount");
const fmtSel = el("fmt"), goBtn = el("go"), statusEl = el("status");
const jobsEl = el("jobs"), metaEl = el("meta");
const setCon = el("setCon"), setTag = el("setTag");
const saveDir = el("saveDir");
const clearBtn = el("clearBtn");
const titleEl = el("title");

const ST_LABEL = { queued: "В очереди", downloading: "Скачиваю", done: "Готово", error: "Ошибка" };

async function api(path, opts) {
  const r = await fetch(SRV + path, opts);
  return r.json();
}

// вес для сортировки: master.m3u8 первым, потом media_N, потом остальные
function rank(u) {
  return /master\.m3u8/i.test(u) ? 0 : /media_\d+\.m3u8/i.test(u) ? 1 : 2;
}

let streams = [];
let pollTimer = null;

function setStatus(msg, cls) {
  statusEl.className = cls || "";
  statusEl.textContent = msg;
}

function renderJobs(jobs, active, queued) {
  jobsEl.innerHTML = ""; // безопасно: список из createElement, без HTML-данных
  if (!jobs.length) {
    const d = document.createElement("div");
    d.className = "empty";
    d.textContent = "Загрузок пока нет";
    jobsEl.appendChild(d);
    metaEl.textContent = "Сервис: работает · идёт " + active + " · в очереди " + queued;
    return;
  }
  jobs.forEach((j) => {
    const d = document.createElement("div");
    d.className = "job " + j.state;
    const head = document.createElement("div");
    head.className = "jhead";
    const st = document.createElement("span");
    st.className = "jstate";
    st.textContent = ST_LABEL[j.state] || j.state;
    const nm = document.createElement("span");
    nm.className = "jname";
    nm.textContent = j.name || j.url.split("/").pop();
    head.appendChild(st);
    head.appendChild(nm);
    d.appendChild(head);
    if (j.state === "downloading") {
      const p = document.createElement("progress");
      p.max = 100;
      p.value = Math.round(j.percent || 0);
      d.appendChild(p);
    }
    if (j.state === "done" && j.filename) {
      const sub = document.createElement("div");
      sub.className = "jsub";
      sub.textContent = j.filename;
      d.appendChild(sub);
    }
    if (j.state === "error" && j.error) {
      const sub = document.createElement("div");
      sub.className = "jsub";
      sub.textContent = j.error;
      d.appendChild(sub);
    }
    jobsEl.appendChild(d);
  });
}

async function refreshJobs() {
  try {
    const r = await api("/jobs");
    renderJobs(r.jobs || [], r.active || 0, r.queued || 0);
    metaEl.textContent = "Сервис: работает · идёт " + (r.active || 0) + " · в очереди " + (r.queued || 0);
  } catch (e) {
    metaEl.textContent = "Сервис не запущен — запустите install.sh и перезапустите расширение";
  }
  pollTimer = setTimeout(refreshJobs, 2000);
}

function applySettings(s) {
  setCon.value = s.max_concurrent;
  setTag.checked = !!s.add_stream_tag;
  saveDir.value = s.save_dir || "~/Downloads";
}

document.addEventListener("DOMContentLoaded", async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab) {
    titleEl.textContent = tab.title || tab.url;
    if (tab.title) nameInput.value = tab.title;
  } else {
    titleEl.textContent = "Нет активной вкладки";
  }
  try {
    const resp = await chrome.runtime.sendMessage({
      type: "getStreams",
      tabId: tab ? tab.id : -1,
    });
    streams = (resp && resp.streams) || [];
  } catch (e) {
    streams = [];
  }
  streams.sort((a, b) => rank(a) - rank(b));
  const seen = [...new Set(streams)];
  streamsSel.innerHTML = ""; // безопасно: очистка списка, новые данные через new Option()
  seen.forEach((u) => streamsSel.add(new Option(u.split("/").pop(), u)));
  streamCount.textContent = seen.length;
  streamsWrap.style.display = seen.length ? "block" : "none";
  if (!seen.length) {
    setStatus("Потоки не найдены — откройте видео на странице, дайте плееру запуститься и откройте расширение снова", "");
  }
  try {
    applySettings(await api("/settings"));
  } catch (e) {}
  refreshJobs();
});

setCon.addEventListener("change", async () => {
  try {
    await api("/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ max_concurrent: Number(setCon.value) || 2 }),
    });
    setStatus("Настройки сохранены", "ok");
  } catch (e) {
    setStatus("Не удалось сохранить настройки", "err");
  }
});

setTag.addEventListener("change", async () => {
  try {
    await api("/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ add_stream_tag: setTag.checked }),
    });
    setStatus("Настройки сохранены", "ok");
  } catch (e) {
    setStatus("Не удалось сохранить настройки", "err");
  }
});

saveDir.addEventListener("change", async () => {
  const v = saveDir.value.trim();
  if (!v) return;
  try {
    const r = await api("/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ save_dir: v }),
    });
    setStatus(r.error ? "❌ " + r.error : "Папка сохранена", r.error ? "err" : "ok");
  } catch (e) {
    setStatus("Не удалось сохранить папку", "err");
  }
});

goBtn.addEventListener("click", async () => {
  if (!streams.length) {
    setStatus("Сначала найдите потоки на странице (откройте видео)", "err");
    return;
  }
  const url = streamsSel.value;
  goBtn.disabled = true;
  setStatus("Добавляю в очередь…");
  try {
    const r = await api("/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, format: fmtSel.value, name: nameInput.value.trim(),
                             save_dir: saveDir.value.trim() }),
    });
    if (!r.ok) {
      setStatus("❌ " + (r.error || "ошибка"), "err");
    } else {
      setStatus("Добавлено в очередь ✔ (" + (ST_LABEL[r.state] || r.state) + ")", "ok");
      refreshJobs();
    }
  } catch (e) {
    setStatus("❌ не удалось связаться с сервисом", "err");
  }
  goBtn.disabled = false;
});

clearBtn.addEventListener("click", async () => {
  try {
    const r = await api("/clear", { method: "POST" });
    setStatus("История очищена (" + (r.removed || 0) + ")", "ok");
    refreshJobs();
  } catch (e) {
    setStatus("Не удалось очистить историю", "err");
  }
});
