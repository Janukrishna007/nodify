# DisasterVision frontend

Next.js App Router dashboard for the real video-analysis service in `../backend`.

Run both servers from the repository root with `powershell -ExecutionPolicy Bypass -File .\start.ps1`. For frontend-only development:

```powershell
npm.cmd ci
npm.cmd run dev -- --hostname 127.0.0.1 --port 3000
```

Open http://127.0.0.1:3000/upload for a new video or drone RTSP connection, or `/dashboard` for the overview. `/` and browser refresh open a fresh upload screen. History remains available through `/sessions`; refresh does not cancel a running analysis. The old `/login` route redirects to upload. This local tool does not implement authentication.

The interface uses shadcn/ui Radix primitives with a white-and-emerald glassmorphism theme, responsive sidebar/navigation sheet, overview metrics, real detection breakdowns, a video analysis console, session search/status filters and an alert center. `/sessions?q=<filename>` supports search. `/alerts` supports acknowledgement. The video console includes saved-frame playback, class filters and downloadable reports and overlays.

Browser notifications are opt-in. Enable or disable them from the analysis console or alert center; the preference persists in this browser. Disabling desktop notifications preserves the dashboard alert history.

The **Drone live stream** tab posts RTSP settings to `/api/streams`. The dashboard displays connection/retry state and real detections/heatmaps while the stream runs. Only the latest 300 analyzed live frames remain in review; full-session summary counts and cumulative heatmaps remain available. Credentials are not saved in the browser or session history. Stop the current source before starting another video or stream.

Uploads are sent as multipart files through the `/api/*` proxy to port 8000. `/dashboard?session=<id>` polls real saved inference results, shows progress and model boxes, supports analyzed-frame review and class filters, and displays current/cumulative heatmaps. Errors are surfaced explicitly, with no mock-data fallback. Completed results remain accessible from history.

The Next.js proxy accepts 501 MB including multipart overhead, with a five-minute request timeout. The frontend and backend enforce a 500 MB file limit. This overrides the default 10 MB body-cloning limit that otherwise truncates large uploads ([Next.js configuration reference](https://nextjs.org/docs/app/api-reference/config/next-config-js/proxyClientMaxBodySize)).

```powershell
npm.cmd run lint
npm.cmd run build -- --webpack
```

See the [project README](../README.md) and [backend API/scoring guide](../backend/README.md) for available models, risk interpretation, limits and validation.
