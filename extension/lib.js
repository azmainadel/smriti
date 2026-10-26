// Shared by the popup, options page and background worker.
export const ext = globalThis.browser ?? globalThis.chrome;

export async function settings() {
  const { apiUrl = "", token = "" } = await ext.storage.local.get(["apiUrl", "token"]);
  return { apiUrl: apiUrl.replace(/\/$/, ""), token };
}

/** The page as the user sees it: rendered DOM (so paywalled and logged-in pages work) and selection. */
export async function capture(tabId) {
  const [{ result }] = await ext.scripting.executeScript({
    target: { tabId },
    func: () => ({
      html: document.documentElement.outerHTML.slice(0, 15_000_000),
      selection: String(window.getSelection() ?? "").trim(),
      title: document.title,
    }),
  });
  return result;
}

export async function save(body) {
  const { apiUrl, token } = await settings();
  if (!apiUrl || !token) throw new Error("Set the API URL and token in the extension options.");
  const res = await fetch(`${apiUrl}/items`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ capture: "extension", ...body }),
  });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json();
}

/** Restricted pages (chrome://, the web store, PDFs in the viewer) cannot be scripted. */
export async function captureOrNull(tab) {
  try {
    return await capture(tab.id);
  } catch {
    return null;
  }
}

export async function flash(tabId, ok) {
  await ext.action.setBadgeBackgroundColor({ color: ok ? "#2f6b3a" : "#a23b2a", tabId });
  await ext.action.setBadgeText({ text: ok ? "✓" : "!", tabId });
  setTimeout(() => ext.action.setBadgeText({ text: "", tabId }), 2500);
}
