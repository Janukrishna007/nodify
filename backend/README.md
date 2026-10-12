# DisasterVision analysis backend

`main.py` is the runnable FastAPI service. `annotate_and_track.py` is a separate manual-annotation experiment and is not needed by the dashboard.

## Run on Windows

From the repository root, `powershell -ExecutionPolicy Bypass -File .\start.ps1` starts the backend and frontend. To run only the backend:

```powershell
cd backend
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

## Pipeline

1. `POST /api/analysis`: multipart video upload, `frame_skip` (default 3), `confidence` (default 0.45). Maximum 500 MB. Input is validated with OpenCV before starting inference.
2. A single background worker decodes the full video sequentially. It saves and analyzes frames 0, N, 2N, etc. It does not invent detections for skipped frames.
3. `ensemble.py` loads the three enabled local checkpoints and runs their predictions. Class-aware NMS suppresses overlapping detections from multiple models.
4. `scoring.py` maps detection centers to a 6-row, 8-column grid. Per class/cell, score = 0.92 × previous score + class weight × confidence × persistence. Persistence counts consecutive analyzed frames, with bonus min(1 + 0.05 × streak, 2).
5. Risk index = score / (1 + score), using a fixed scale. Cumulative risk uses mean weighted evidence over analyzed frames, transformed with the same function. Frames with no detections contribute zero evidence; current risk decays.
6. Raw JPEGs, heatmap JPEGs, cumulative overlays, and per-frame JSON are stored under `data/<session-id>/`. Session progress and results persist across browser refreshes and backend restarts. Interrupted sessions are marked failed after a restart.

### Checkpoints and interpretation

| File | Verified raw labels | Used outputs |
| --- | --- | --- |
| `fire_and_smoke_3.pt` | smoke, fire | smoke, fire |
| `smoke_fire_roboflow.pt` | fire | fire |
| `best_flood.pt` | flood, non_water, occlusion, water | flood only |

Ordinary `water` predictions are excluded: they are not proof of flood damage. Fire weight = 0.9, smoke = 0.6, flood = 0.7. No trained structural damage, collapsed-building or debris model is bundled. Model confidence is not a validated physical damage measurement. Counts represent detections across frames, not unique tracked objects.

Heatmaps use camera-frame coordinates. The cumulative grid is temporal evidence at image positions, not a geographic damage map. Moving drone footage needs camera registration/geolocation before aggregation into a real map. There is no ByteTrack interpolation in this upload pipeline.

## API

- `GET /api/health`: available models, active session, grid.
- `GET /api/sessions`: saved analysis history.
- `GET /api/sessions/{id}`: progress, counts, latest index, cumulative cells, errors.
- `GET /api/sessions/{id}/frames/{index}`: results for a saved analyzed frame (index starts at zero).
- `GET /api/sessions/{id}/frames/{index}/image`, `/heatmap`, `/cumulative`: JPEG outputs.
- `GET /api/sessions/{id}/report`: complete JSON report.
- `POST /api/sessions/{id}/cancel`: stop at the next inference boundary; retain partial results.
- `WS /ws/sessions/{id}`: latest session/frame updates. The frontend uses REST polling so refresh/reconnect works without WebSocket proxy configuration.

Only one analysis runs at a time; a concurrent start returns HTTP 409. Missing weights and inference errors fail the session explicitly. No random-data fallback is used. API reference: http://127.0.0.1:8000/docs.

## Validation

```powershell
.\.venv\Scripts\python.exe -m unittest test_scoring -v
# Both servers must be running:
.\.venv\Scripts\python.exe smoke_test.py --video flood_footage.mp4.webm
# Optional browser validation dependency:
.\.venv\Scripts\python.exe -m pip install playwright
.\.venv\Scripts\python.exe browser_test.py
# Regression test with a video larger than 10 MB (stops the test analysis by default):
.\.venv\Scripts\python.exe large_upload_test.py "C:\path\to\large-video.mp4"
```

The smoke test creates a 30-frame clip, uploads it through the frontend proxy, checks sample indices, waits for real inference, validates reports and decoded heatmap images, and rejects an invalid video. The browser test uses installed Microsoft Edge and uploads that clip through the UI, verifies frame navigation, filters, heatmap toggling, download, and refresh.

Implementation references: [Ultralytics prediction API](https://docs.ultralytics.com/modes/predict/), [FastAPI file uploads](https://fastapi.tiangolo.com/tutorial/request-files/).
