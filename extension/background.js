// Фон: перехватывает сетевые запросы страниц и запоминает найденные .m3u8 (по вкладкам)
const KEY = "capturedStreams";
const MAX_PER_TAB = 30;

chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.session.set({ [KEY]: {} }).catch(() => {});
});

chrome.webRequest.onBeforeRequest.addListener(
  (d) => {
    const u = d.url || "";
    if (!/\.m3u8(\?|$)/i.test(u) || d.tabId < 0) return;
    chrome.storage.session.get(KEY).then((data) => {
      const map = data[KEY] || {};
      let arr = map[d.tabId] || [];
      if (!arr.includes(u)) {
        arr.push(u);
        if (arr.length > MAX_PER_TAB) arr = arr.slice(-MAX_PER_TAB);
        map[d.tabId] = arr;
        chrome.storage.session.set({ [KEY]: map }).catch(() => {});
      }
    }).catch(() => {});
  },
  { urls: ["<all_urls>"], types: ["xmlhttprequest", "media", "object", "other"] }
);

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg && msg.type === "getStreams") {
    chrome.storage.session.get(KEY).then((data) => {
      sendResponse({ streams: (data[KEY] || {})[msg.tabId] || [] });
    }).catch(() => sendResponse({ streams: [] }));
    return true; // async
  }
});

// при перезагрузке/переходе на другую страницу — сбрасываем потоки вкладки,
// чтобы в списке не оставались ссылки с прошлых страниц
chrome.tabs.onUpdated.addListener((tabId, changeInfo) => {
  if (changeInfo && changeInfo.status === "loading") {
    chrome.storage.session.get(KEY).then((data) => {
      const map = data[KEY] || {};
      if (map[tabId]) {
        delete map[tabId];
        chrome.storage.session.set({ [KEY]: map }).catch(() => {});
      }
    }).catch(() => {});
  }
});

chrome.tabs.onRemoved.addListener((tabId) => {
  chrome.storage.session.get(KEY).then((data) => {
    const map = data[KEY] || {};
    if (map[tabId]) {
      delete map[tabId];
      chrome.storage.session.set({ [KEY]: map }).catch(() => {});
    }
  }).catch(() => {});
});
