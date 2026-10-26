import { ext, settings } from "./lib.js";

const $ = (id) => document.getElementById(id);
const current = await settings();
$("apiUrl").value = current.apiUrl || "http://localhost:8000";
$("token").value = current.token;

$("form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const apiUrl = $("apiUrl").value.trim().replace(/\/$/, "");
  const token = $("token").value.trim();
  // Ask for access to just the Smriti server, not every site.
  const origin = `${new URL(apiUrl).origin}/*`;
  const granted = await ext.permissions.request({ origins: [origin] });
  if (!granted) {
    $("status").textContent = "Permission to reach the server was refused.";
    return;
  }
  await ext.storage.local.set({ apiUrl, token });
  try {
    const res = await fetch(`${apiUrl}/auth/me`, { headers: { Authorization: `Bearer ${token}` } });
    $("status").textContent = res.ok ? `Connected as “${(await res.json()).name}”.` : `The server said ${res.status}. Check the token.`;
  } catch {
    $("status").textContent = "Can't reach that URL.";
  }
});
