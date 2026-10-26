import createClient, { type Middleware } from "openapi-fetch";
import { getToken, setToken } from "./auth";
import { API_URL } from "./config";
import type { components, paths } from "./schema";

export type Item = components["schemas"]["ItemOut"];
export type ItemDetail = components["schemas"]["ItemDetail"];
export type ItemPage = components["schemas"]["ItemPage"];
export type SearchOut = components["schemas"]["SearchOut"];
export type Chip = components["schemas"]["ChipOut"];
export type Resurfaced = components["schemas"]["Resurfaced"];
export type ItemCreate = components["schemas"]["ItemCreate"];
export type TokenOut = components["schemas"]["TokenOut"];

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

const auth: Middleware = {
  onRequest({ request }) {
    const token = getToken();
    if (token) request.headers.set("Authorization", `Bearer ${token}`);
    return request;
  },
  onResponse({ response }) {
    if (response.status === 401 && getToken()) setToken(null);
    return response;
  },
};

export const api = createClient<paths>({ baseUrl: API_URL });
api.use(auth);

/** Unwrap an openapi-fetch result or throw, so TanStack Query sees errors. */
export async function call<T>(
  promise: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  const { data, error, response } = await promise;
  if (error !== undefined || !response.ok) {
    const detail = (error as { detail?: unknown } | undefined)?.detail;
    throw new ApiError(response.status, typeof detail === "string" ? detail : response.statusText);
  }
  return data as T;
}

/** Multipart upload (the generated client types JSON bodies only). */
export async function uploadFile(file: File, extra: Record<string, string> = {}): Promise<Item> {
  const body = new FormData();
  body.set("file", file);
  for (const [k, v] of Object.entries(extra)) body.set(k, v);
  const res = await fetch(`${API_URL}/items`, {
    method: "POST",
    body,
    headers: { Authorization: `Bearer ${getToken() ?? ""}` },
  });
  if (!res.ok) throw new ApiError(res.status, await res.text());
  return res.json();
}

export async function importFile(file: File): Promise<components["schemas"]["ImportOut"]> {
  const body = new FormData();
  body.set("file", file);
  const res = await fetch(`${API_URL}/import`, {
    method: "POST",
    body,
    headers: { Authorization: `Bearer ${getToken() ?? ""}` },
  });
  if (!res.ok) throw new ApiError(res.status, await res.text());
  return res.json();
}

export async function downloadExport(): Promise<void> {
  const res = await fetch(`${API_URL}/export`, { headers: { Authorization: `Bearer ${getToken() ?? ""}` } });
  if (!res.ok) throw new ApiError(res.status, res.statusText);
  const url = URL.createObjectURL(await res.blob());
  const a = Object.assign(document.createElement("a"), { href: url, download: "smriti-export.zip" });
  a.click();
  URL.revokeObjectURL(url);
}
