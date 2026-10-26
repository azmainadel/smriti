# Capture

Every client is thin: it sends what it has to `POST /items` and the server does the rest. Each device gets its own token from Settings → Devices.

## Browser extension

See [extension/README.md](../extension/README.md). It sends the rendered page, so pages behind a login or paywall are saved as you see them.

## Android

Open the web app in Chrome and install it (menu → Install app). Smriti then shows up in the share sheet. Links and text open a small panel with a note field; Enter saves and the panel closes a second later. Shared files (images, PDFs) are handed over by the service worker and uploaded the same way.

## iPhone and iPad

iOS does not support the Web Share Target API, so use a Shortcut:

1. New Shortcut → turn on **Show in Share Sheet**, accept URLs, text and images.
2. Add **Get Contents of URL**:
   - URL: `https://your-host/items`
   - Method: POST
   - Headers: `Authorization: Bearer smr_...`
   - Request body: JSON, with `url` set to **Shortcut Input** and `capture` set to `share`
3. For images, use a second branch with Request body: Form, field `file` set to **Shortcut Input**.

## Email

Point your mail provider's inbound webhook at

```
POST https://your-host/inbound/email/<SMRITI_INBOUND_EMAIL_SECRET>
```

Postmark, Mailgun and SendGrid payloads work as they come, as does plain JSON with `subject`, `text`, `html` and `attachments`. Each URL in the body becomes an item (up to 5) with the rest of the body as its note. A body without URLs becomes a note titled by the subject. Attachments become file items. Quoted replies and signatures are dropped.

## CLI

```sh
uv tool install ./api        # or: cd api && uv run smriti ...
smriti login --url https://your-host
smriti save https://example.com/essay -n "for the reading group" -t essays
smriti save ./paper.pdf
pbpaste | smriti save -
smriti import bookmarks.html   # also Pocket and Raindrop exports
smriti search "that blue chart about retention"
smriti export -o backup.zip
```

## Import

Settings → Import, the first-run screen, `smriti import` and `POST /import` all accept:

- Netscape bookmark files from Chrome, Firefox and Safari. Folder names become tags; `<DD>` descriptions become notes.
- Pocket exports (HTML or CSV).
- Raindrop CSV exports. Notes and highlights become the note; folders and tags become tags.

Original save dates are kept. URLs already in the library are skipped.
