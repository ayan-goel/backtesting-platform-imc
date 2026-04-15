// Server-side API proxy. Browser code hits /api/*; this handler attaches the API key
// and forwards to the FastAPI service. The key never ships to the browser.
//
// We forward the raw request body (ArrayBuffer) so multipart uploads work without
// re-encoding. For multipart, we explicitly preserve the incoming Content-Type header
// (which includes the boundary string). For JSON or empty bodies we also pass it
// through unchanged.

const API_URL = process.env.PLATFORM_API_URL ?? "http://localhost:8000";
const API_KEY = process.env.PLATFORM_API_KEY ?? "";

export const dynamic = "force-dynamic";

type Ctx = { params: Promise<{ path: string[] }> };

async function forward(req: Request, ctx: Ctx): Promise<Response> {
  const { path } = await ctx.params;
  const pathStr = "/" + path.join("/");
  const url = new URL(req.url);
  const qs = url.searchParams.toString();
  const fullPath = qs ? `${pathStr}?${qs}` : pathStr;

  const headers: Record<string, string> = {
    "X-API-Key": API_KEY,
  };
  const contentType = req.headers.get("content-type");
  if (contentType) headers["content-type"] = contentType;

  const init: RequestInit = {
    method: req.method,
    headers,
    cache: "no-store",
  };

  if (req.method !== "GET" && req.method !== "HEAD") {
    // Buffer the body so we don't need `duplex: 'half'` and it works with any content type.
    init.body = await req.arrayBuffer();
  }

  const upstream = await fetch(`${API_URL}${fullPath}`, init);

  // Next's fetch auto-decompresses gzipped upstream bodies via undici, but
  // preserves the `content-encoding` / `content-length` headers from the
  // original compressed response. Forwarding those headers unchanged makes
  // the browser try to re-decompress plaintext and fail with
  // ERR_CONTENT_DECODING_FAILED. Strip them; let the runtime set a correct
  // Content-Length (or omit it for streams).
  const responseHeaders = new Headers(upstream.headers);
  responseHeaders.delete("content-encoding");
  responseHeaders.delete("content-length");

  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: responseHeaders,
  });
}

export async function GET(req: Request, ctx: Ctx) {
  return forward(req, ctx);
}
export async function POST(req: Request, ctx: Ctx) {
  return forward(req, ctx);
}
export async function PUT(req: Request, ctx: Ctx) {
  return forward(req, ctx);
}
export async function DELETE(req: Request, ctx: Ctx) {
  return forward(req, ctx);
}
