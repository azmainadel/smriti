/**
 * Extracted article HTML comes from arbitrary web pages. The server already strips scripts,
 * but the reader renders it inline, so the client keeps an allowlist as a second fence.
 */
const ALLOWED = new Set([
  "p", "br", "hr", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li", "blockquote", "pre", "code",
  "em", "strong", "b", "i", "u", "s", "sub", "sup", "small", "mark", "a", "img", "figure", "figcaption",
  "table", "thead", "tbody", "tr", "th", "td", "dl", "dt", "dd", "div", "span", "section", "article",
]);
const ATTRS: Record<string, string[]> = { a: ["href", "title"], img: ["src", "alt", "title"], "*": ["data-t", "data-page"] };

function safeUrl(url: string): boolean {
  return /^(https?:|data:image\/(png|jpe?g|gif|webp);)/i.test(url.trim());
}

export function sanitize(html: string): string {
  if (typeof window === "undefined") return "";
  const doc = new DOMParser().parseFromString(`<body>${html}</body>`, "text/html");
  const walk = (node: Element) => {
    for (const child of Array.from(node.children)) {
      const tag = child.tagName.toLowerCase();
      if (!ALLOWED.has(tag)) {
        if (["script", "style", "iframe", "object", "embed", "form", "svg", "math"].includes(tag)) child.remove();
        else {
          walk(child);
          child.replaceWith(...Array.from(child.childNodes));
        }
        continue;
      }
      for (const attr of Array.from(child.attributes)) {
        const allowed = [...(ATTRS[tag] ?? []), ...(ATTRS["*"] ?? [])];
        if (!allowed.includes(attr.name) || ((attr.name === "href" || attr.name === "src") && !safeUrl(attr.value))) {
          child.removeAttribute(attr.name);
        }
      }
      if (tag === "a") {
        child.setAttribute("target", "_blank");
        child.setAttribute("rel", "noopener noreferrer nofollow");
      }
      if (tag === "img") child.setAttribute("loading", "lazy");
      walk(child);
    }
  };
  walk(doc.body);
  return doc.body.innerHTML;
}
