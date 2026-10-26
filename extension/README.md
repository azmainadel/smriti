# Smriti browser extension

Manifest V3, one codebase for Chrome and Firefox. It only captures: the server does all the work.

- **Toolbar button or Alt+Shift+S**: preview, add a note, Enter to save. The panel closes itself a second later.
- **Alt+Shift+D**: save the current page without the panel.
- **Right-click**: save the page, a link, a text selection (as a quote) or an image.

The extension sends the page's rendered HTML, so paywalled and logged-in pages are saved as you see them, and the server rarely needs to fetch anything.

## Install

1. In Smriti, open Settings → Devices and create a token named after this browser.
2. Chrome: `chrome://extensions` → Developer mode → Load unpacked → pick this folder.
   Firefox: `about:debugging#/runtime/this-firefox` → Load Temporary Add-on → pick `manifest.json`.
3. In the extension options, paste the API URL and the token. It asks for permission to reach that one server.

To package: `zip -r smriti-extension.zip . -x README.md`.
