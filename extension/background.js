import { captureOrNull, ext, flash, save } from "./lib.js";

ext.runtime.onInstalled.addListener(() => {
  ext.contextMenus.create({ id: "page", title: "Save page to Smriti", contexts: ["page", "link"] });
  ext.contextMenus.create({ id: "selection", title: "Save selection to Smriti", contexts: ["selection"] });
  ext.contextMenus.create({ id: "image", title: "Save image to Smriti", contexts: ["image"] });
  ext.storage.local.get("apiUrl").then(({ apiUrl }) => apiUrl || ext.runtime.openOptionsPage());
});

ext.contextMenus.onClicked.addListener(async (info, tab) => {
  try {
    if (info.menuItemId === "selection") {
      await save({ url: tab.url, title: tab.title, selection: info.selectionText });
    } else if (info.menuItemId === "image") {
      await save({ url: tab.url, image_url: info.srcUrl });
    } else if (info.linkUrl) {
      await save({ url: info.linkUrl });
    } else {
      const page = await captureOrNull(tab);
      await save({ url: tab.url, title: page?.title ?? tab.title, html: page?.html ?? null });
    }
    await flash(tab.id, true);
  } catch (e) {
    console.error(e);
    await flash(tab.id, false);
  }
});

ext.commands.onCommand.addListener(async (command, tab) => {
  if (command !== "quick-save") return;
  tab ??= (await ext.tabs.query({ active: true, currentWindow: true }))[0];
  try {
    const page = await captureOrNull(tab);
    await save({ url: tab.url, title: page?.title ?? tab.title, html: page?.html ?? null });
    await flash(tab.id, true);
  } catch (e) {
    console.error(e);
    await flash(tab.id, false);
  }
});
