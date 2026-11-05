// Ищет на странице ссылки на HLS-плейлисты (.m3u8) и отдаёт их попапу
(function () {
  const found = new Set();

  function scan() {
    try {
      performance.getEntriesByType("resource").forEach((e) => {
        if (/\.m3u8(\?|$)/i.test(e.name)) found.add(e.name.split("?")[0]);
      });
    } catch (e) {}
    document.querySelectorAll("video, source, audio, a[href]").forEach((el) => {
      const raw = el.src || (el.href && el.getAttribute("href"));
      if (!raw) return;
      try {
        const u = new URL(raw, location.href).href;
        if (/\.m3u8(\?|$)/i.test(u)) found.add(u.split("?")[0]);
      } catch (e) {}
    });
  }

  scan();
  setTimeout(scan, 1500);
  window.addEventListener("load", () => setTimeout(scan, 800));

  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    if (msg && msg.type === "getM3u8") {
      scan();
      sendResponse({ urls: [...found] });
    }
    return true;
  });
})();
