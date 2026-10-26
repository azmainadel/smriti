import { captureOrNull, ext, save } from "./lib.js";

const $ = (id) => document.getElementById(id);
const [tab] = await ext.tabs.query({ active: true, currentWindow: true });
const page = await captureOrNull(tab);

$("title").textContent = page?.title || tab.title || tab.url;
$("url").textContent = tab.url;
if (tab.favIconUrl) $("favicon").src = tab.favIconUrl;
else $("favicon").hidden = true;
if (page?.selection) {
  $("selection").textContent = page.selection.slice(0, 400);
  $("selection").hidden = false;
  $("asQuote").checked = true;
} else {
  $("asQuote").parentElement.hidden = true;
}

async function submit() {
  $("save").disabled = true;
  $("status").textContent = "Saving…";
  const note = $("note").value.trim() || null;
  try {
    if ($("asQuote").checked && page?.selection) {
      await save({ url: tab.url, title: page.title, selection: page.selection, note });
    } else {
      await save({ url: tab.url, title: page?.title ?? tab.title, html: page?.html ?? null, note });
    }
    $("status").textContent = "Saved ✓";
    document.body.classList.add("done");
    setTimeout(() => window.close(), 1000);
  } catch (e) {
    $("status").textContent = String(e.message ?? e);
    $("status").classList.add("error");
    $("save").disabled = false;
  }
}

$("form").addEventListener("submit", (e) => {
  e.preventDefault();
  submit();
});
$("note").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    submit();
  }
});
