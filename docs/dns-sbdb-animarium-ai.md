# DNS setup — sbdb.animarium.ai

Point the public FastAPI hostname at Railway. Keep Supabase on its default project host (`*.supabase.co`); the app connects with `DATABASE_URL`.

## 1. Railway

1. Create/select the FastAPI service (stage 4+).
2. **Settings → Networking → Custom domain** → add `sbdb.animarium.ai`.
3. Copy the target Railway shows (usually a **CNAME** host like `*.up.railway.app`, or their current custom-domain instructions).
4. Leave Railway’s managed TLS on (certificate issues after DNS propagates).

## 2. DNS at animarium.ai

At the DNS host for `animarium.ai` (registrar or Cloudflare/etc.):

| Type | Name / host | Value | TTL |
| --- | --- | --- | --- |
| **CNAME** | `sbdb` | Railway-provided target (from step 1) | Auto / 300s |

Notes:
- Prefer **CNAME** for a subdomain; use an **A/ALIAS** only if your DNS UI requires it and Railway documents an IP/ALIAS.
- If the zone is on Cloudflare, start with **DNS only** (grey cloud) until the Railway cert is issued, then proxy if you want.
- Do **not** point `sbdb` at Supabase’s DB host — that is not the HTTP API.

## 3. App config

- Set Railway public URL / `ALLOWED_HOSTS` (or equivalent) to include `sbdb.animarium.ai`.
- CORS: allow only origins you need (often none for a pure API).
- Health check: `https://sbdb.animarium.ai/health` after deploy (stage 7/8).

## 4. Verify

```bash
dig +short CNAME sbdb.animarium.ai
curl -sS https://sbdb.animarium.ai/health
```

Propagation is often minutes; certs can lag DNS by a short while.

## Free-tier note

Custom domains on Railway Free/Trial are fine for this hostname; no extra DNS cost if `animarium.ai` is already yours. Supabase Free does not need a custom domain for this sample.
