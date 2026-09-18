import { ApiError, type ApiErrorBody } from "@/lib/api/types";

const API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "";

function buildUrl(path: string): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  if (!API_BASE_URL) {
    return normalizedPath;
  }
  return `${API_BASE_URL.replace(/\/$/, "")}${normalizedPath}`;
}

async function parseError(response: Response): Promise<ApiError> {
  let body: ApiErrorBody | null = null;
  try {
    body = (await response.json()) as ApiErrorBody;
  } catch {
    body = null;
  }

  const detail = body?.detail;
  if (detail && typeof detail === "object" && !Array.isArray(detail)) {
    const message =
      typeof detail.message === "string" && detail.message.trim()
        ? detail.message
        : "Unable to load matches. Please try again.";
    const code = typeof detail.code === "string" ? detail.code : undefined;
    return new ApiError(message, response.status, code);
  }

  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0];
    const message =
      typeof first?.msg === "string" && first.msg.trim()
        ? first.msg
        : "Unable to load matches. Please try again.";
    return new ApiError(message, response.status);
  }

  if (typeof detail === "string" && detail.trim()) {
    return new ApiError(detail, response.status);
  }

  return new ApiError(
    "Unable to load matches. Please try again.",
    response.status,
  );
}

export async function apiRequest<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(buildUrl(path), {
      ...init,
      headers: {
        Accept: "application/json",
        ...init?.headers,
      },
    });
  } catch {
    throw new ApiError("Unable to load matches. Please try again.", 0);
  }

  if (!response.ok) {
    throw await parseError(response);
  }

  return (await response.json()) as T;
}
