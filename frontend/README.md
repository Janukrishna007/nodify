# DisasterVision frontend

Next.js App Router dashboard for the real video-analysis service in `../backend`.

Run both servers from the repository root with `powershell -ExecutionPolicy Bypass -File .\start.ps1`. For frontend-only development:

```powershell
npm.cmd ci
npm.cmd run dev -- --hostname 127.0.0.1 --port 3000
```

Open http://127.0.0.1:3000/upload. `/` and the old `/login` route redirect to upload; this local tool does not implement authentication.

Uploads are sent as multipart files through the `/api/*` proxy to port 8000. `/dashboard?session=<id>` polls real saved inference results, shows progress and model boxes, supports analyzed-frame review and class filters, and displays current/cumulative heatmaps. Errors are surfaced explicitly, with no mock-data fallback. Completed results remain accessible from history.

The Next.js proxy accepts 501 MB including multipart overhead, with a five-minute request timeout. The frontend and backend enforce a 500 MB file limit. This overrides the default 10 MB body-cloning limit that otherwise truncates large uploads ([Next.js configuration reference](https://nextjs.org/docs/app/api-reference/config/next-config-js/proxyClientMaxBodySize)).

```powershell
npm.cmd run lint
npm.cmd run build -- --webpack
```

See the [project README](../README.md) and [backend API/scoring guide](../backend/README.md) for available models, risk interpretation, limits and validation.
