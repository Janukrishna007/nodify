# Nodify / DisasterVision

Upload recorded disaster footage, analyze sampled frames using the bundled YOLO models, and inspect detections and risk heatmaps in a Next.js dashboard.

## Run

Requirements: Node.js 20.9+ and Python 3.10+. CPU inference works; a supported GPU can improve speed.

From the repository root on Windows:

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

Open **http://127.0.0.1:3000/upload**. The launcher installs missing dependencies and starts both servers with logs under `.logs/`.

To run manually, use two terminals:

```powershell
# Terminal 1
cd backend
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

```powershell
# Terminal 2
cd frontend
npm.cmd ci
npm.cmd run dev -- --hostname 127.0.0.1 --port 3000
```

The development script uses Webpack to avoid the Turbopack worker/resource crash observed on this Windows machine.

## Use the application

1. Choose or drop a video (MP4, MOV, AVI, WebM, MKV or M4V; maximum 500 MB).
2. Set the frame interval (default: every third frame) and minimum confidence (default: 45%).
3. Select **Start analysis**. The video is uploaded to the backend and decoded sequentially; sampled frames are saved and run through all three specialist models.
4. Watch progress, detection boxes and the current risk grid. Filter fire, smoke and flood independently.
5. Review saved analyzed frames with the slider or Previous/Next buttons. **Follow latest** returns to the newest result.
6. Inspect the cumulative heatmap and download heatmap JPEGs or the full JSON report.
7. Reopen an analysis from upload-page history. Results survive browser refreshes and backend restarts. **Stop analysis** preserves partial results.

## What is actually detected

| Bundled checkpoint | Verified labels | Reported disaster classes |
| --- | --- | --- |
| `backend/models_light/fire_and_smoke_3.pt` | smoke, fire | smoke, fire |
| `backend/models_light/smoke_fire_roboflow.pt` | fire | fire |
| `backend/models_light/best_flood.pt` | flood, non_water, occlusion, water | flood |

Overlapping same-class predictions are merged by NMS. Ordinary water/background/occlusion predictions are excluded. The repository does **not** contain trained structural-damage, collapse or debris detectors. The previous `best_2.pt` registry entry was missing and now points to the verified fire/smoke checkpoint.

There are no random frames, stock-photo feeds or synthetic risk scores in the analysis dashboard. A no-detection result is shown explicitly. Corrupt videos, model failures and decode errors produce visible errors.

## Heatmap meaning

Detections map by bounding-box center to an **8-column × 6-row** image grid. Per-cell scoring combines class weight (fire 0.9, smoke 0.6, flood 0.7), model confidence and consecutive-frame persistence. Current scores decay by 0.92 on each analyzed frame. The persistence multiplier is capped at 2.

The displayed risk index uses `score / (1 + score)`, on a fixed scale from zero toward one. Cumulative risk uses mean weighted evidence across analyzed frames. All class filters affect the visible current and cumulative grids; downloaded overlays include all classes.

Risk is a heuristic evidence index, **not measured physical damage or an accuracy guarantee**. Counts are detections across sampled frames, not unique tracked objects. The grid uses camera-frame coordinates. A geographic damage map from moving drone footage requires registration/geolocation; this pipeline does not provide it. Skipped frames are not inferred or interpolated.

## Structure

```text
backend/
  main.py          Upload, analysis worker, progress/history, images, reports
  ensemble.py      Local model loading, inference and class-aware NMS
  config.py        Sampling, limits and grid settings
  scoring.py       Current/cumulative risk and heatmap rendering
  requirements.txt
  data/            Uploaded footage and saved results (ignored)
frontend/src/
  app/upload/      Real video upload, analysis settings and history
  app/dashboard/   Analysis-session view
  components/      Frame viewer, boxes, filters and heatmaps
  services/        Real REST upload and result polling
start.ps1          Launch both local servers
```

See [backend documentation](backend/README.md) for API, scoring and validation details. API documentation: http://127.0.0.1:8000/docs. The original hackathon architecture/dataset proposal is preserved in [docs/design-proposal.md](docs/design-proposal.md); its mock UI and planned features describe the earlier prototype.

## Check the pipeline

```powershell
cd backend
.\.venv\Scripts\python.exe -m unittest test_scoring -v
# With both servers running:
.\.venv\Scripts\python.exe smoke_test.py --video flood_footage.mp4.webm
```

The smoke test uploads a short clip through the frontend proxy and validates real inference, sampled frame indices, heatmap images, reports and invalid-video rejection. Browser validation is described in [backend/README.md](backend/README.md).

Built for CodeReCET 2026, CET Hackathon powered by Armada.

## Repository assets and notebooks

Model weights and videos are stored with Git LFS. Install Git LFS before cloning, or run `git lfs pull` after cloning to download these assets.

The Roboflow notebooks in `TEMPLATE/` read the API key from the `ROBOFLOW_API_KEY` environment variable. Set it before running those notebooks; credentials are not stored in the repository.
