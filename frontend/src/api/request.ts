export type ApiFetch = (path: string, init?: RequestInit) => Promise<Response>;

export class ApiError extends Error {
  status: number;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
  }
}

export async function apiRequest<T>(apiFetch: ApiFetch, path: string, init?: RequestInit): Promise<T> {
  const response = await apiFetch(path, init);

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") {
        detail = body.detail;
      } else if (Array.isArray(body.detail)) {
        // FastAPI's built-in RequestValidationError shape: a list of
        // { loc, msg, type } objects rather than a plain string.
        const messages = body.detail
          .map((item) => {
            if (item && typeof item === "object" && "msg" in item) {
              const { loc, msg } = item as { loc?: unknown; msg?: unknown };
              const path = Array.isArray(loc) ? loc.join(".") : undefined;
              return path ? `${path}: ${String(msg)}` : String(msg);
            }
            return undefined;
          })
          .filter((message): message is string => Boolean(message));
        if (messages.length > 0) detail = messages.join("; ");
      }
    } catch {
      // response body wasn't JSON; fall back to statusText
    }
    throw new ApiError(response.status, detail);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export function jsonInit(method: string, body: unknown): RequestInit {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}
