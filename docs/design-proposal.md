# Nodify
Autonomous Drone based Damage mapping — Nodify | Code Recet powered by Armada

# DisasterVision 

**Autonomous Drone-Based Disaster Intelligence System**

Problem Statement: Q3) Autonomous Drone-based Disaster Intelligence for Damage Mapping and Rapid Response

---

## What It Does

DisasterVision is an end-to-end AI inference pipeline that ingests aerial drone video footage from disaster-affected zones and produces a near real-time spatial impact heatmap on a live web dashboard.

Instead of having human analysts review hours of raw drone footage, DisasterVision automatically detects disaster damage, scores its severity, and presents operators with a single color-coded map of the zone, which gets updated continuously as new footage streams in.

---


# DisasterVision Frontend

DisasterVision is a desktop-first disaster analysis dashboard built with Next.js App Router, TypeScript, Tailwind CSS, Framer Motion, and Zustand.

The frontend is designed for a control-room workflow:
- operator login
- video or RTSP ingest setup
- live damage monitoring
- cumulative heatmap review
- annotation capture
- historical session playback

## Features

- Minimal black-and-white futuristic dashboard UI
- Glassmorphism panels and subtle motion
- Mock login flow with redirect to dashboard
- Upload page for file or RTSP input
- Live analysis dashboard with:
  - incoming frame display
  - zone bounding boxes
  - heatmap overlay
  - damage filters
  - cumulative heatmap panel
  - annotation modal
- Session history and playback viewer
- Mock API and WebSocket service layer ready for backend replacement

## Tech Stack

- `Next.js` App Router for routing and app structure
- `TypeScript` for typed components, services, and domain models
- `Tailwind CSS` for styling and layout
- `Framer Motion` for page transitions and micro-interactions
- `Zustand` for client-side session and dashboard state

## Routes

- `/login`  
  Invite-only / SSO-style mock login screen

- `/upload`  
  Choose between file upload and RTSP stream input

- `/dashboard`  
  Main analysis console with live feed, filters, zones, and heatmaps

- `/sessions`  
  Session history list

- `/sessions/[id]`  
  Playback viewer for a past analysis session

## Recommended Repository Structure

```text
disastervision/
├── backend/
│   ├── main.py                     # FastAPI app + WebSocket endpoints
│   ├── pipeline.py                 # Frame reader + inference workers
│   ├── grid.py                     # Grid scoring logic
│   ├── heatmap.py                  # Heatmap generation and blending
│   └── config.py                   # Thresholds, weights, grid constants
├── frontend/
│   ├── app/
│   │   ├── api/
│   │   │   └── annotations/
│   │   │       └── route.ts        # Mock annotation POST route
│   │   ├── dashboard/
│   │   │   └── page.tsx            # Main live dashboard
│   │   ├── login/
│   │   │   └── page.tsx            # Login page
│   │   ├── sessions/
│   │   │   ├── [id]/
│   │   │   │   └── page.tsx        # Playback view for one session
│   │   │   └── page.tsx            # Session history page
│   │   ├── upload/
│   │   │   └── page.tsx            # Upload / RTSP setup page
│   │   ├── globals.css             # Global theme and utility styles
│   │   ├── layout.tsx              # Root layout and fonts
│   │   ├── loading.tsx             # Global loading skeleton
│   │   └── page.tsx                # Redirects to /login
│   ├── components/
│   │   ├── annotations/
│   │   │   └── AnnotationModal.tsx
│   │   ├── auth/
│   │   │   └── AuthGate.tsx
│   │   ├── common/
│   │   │   ├── AnimatedGridBackground.tsx
│   │   │   ├── MotionScreen.tsx
│   │   │   └── Panel.tsx
│   │   ├── dashboard/
│   │   │   ├── CumulativeHeatmapPanel.tsx
│   │   │   ├── Filters.tsx
│   │   │   ├── Sidebar.tsx
│   │   │   └── ZoneCard.tsx
│   │   ├── session/
│   │   │   ├── PlaybackViewer.tsx
│   │   │   └── SessionList.tsx
│   │   └── video/
│   │       ├── BoundingBox.tsx
│   │       ├── HeatmapOverlay.tsx
│   │       └── VideoFeed.tsx
│   ├── lib/
│   │   └── utils.ts                # Helper utilities
│   ├── services/
│   │   ├── api.ts                  # REST API abstraction layer
│   │   ├── mock-data.ts            # Mock frames, zones, sessions
│   │   └── socket.ts               # WebSocket abstraction layer
│   ├── store/
│   │   └── disaster-store.ts       # Zustand store
│   ├── types/
│   │   └── index.ts                # Shared domain types
│   ├── package.json
│   ├── tailwind.config.ts
│   ├── tsconfig.json
│   └── next.config.ts
├── dataset/
│   ├── images/
│   │   ├── train/
│   │   ├── val/
│   │   └── test/
│   ├── labels/
│   │   ├── train/
│   │   ├── val/
│   │   └── test/
│   └── data.yaml
├── models/
│   └── yolo11l_disaster.pt         # Fine-tuned YOLO weights
├── docker-compose.yml
└── README.md
```

## Frontend Folder Breakdown

Inside `frontend/`, the structure is organized by responsibility:

- `app/`  
  App Router pages, route handlers, layout, and global styling

- `components/`  
  Reusable UI modules grouped by feature area such as video, dashboard, session, auth, and annotations

- `services/`  
  Backend-facing integration layer for HTTP and WebSocket communication

- `store/`  
  Shared client-side dashboard state using Zustand

- `types/`  
  Shared TypeScript interfaces for zones, frames, sessions, annotations, and filters

- `lib/`  
  Utility helpers such as class merging, formatting, and small math helpers

## How the Frontend Works

### 1. Live Feed Rendering

The live feed currently renders a simulated frame image inside `VideoFeed.tsx`.

On top of that image, the UI places:
- bounding boxes for detected zones
- a heatmap grid overlay
- annotation click handling

### 2. Is It Using Canvas?

Right now, **no canvas is used**.

The current implementation uses:
- a regular image element for the frame
- absolutely positioned React components for bounding boxes
- a CSS grid of animated `div`s for the heatmap

This is a good choice for:
- fast UI iteration
- easier styling with Tailwind
- clickable overlays
- readable hackathon/demo code

### 3. When Should You Use Canvas Instead?

You may want to switch to `canvas` if:
- frame rate becomes high
- the number of boxes becomes very large
- you need pixel-level drawing
- you want smoother rendering for continuous video streams

In short:
- current project = DOM overlays
- higher-performance production video pipeline = canvas is a strong option

## Backend Integration Guide

The frontend is already structured to connect cleanly to a backend.

### API Layer

Use [`services/api.ts`](./services/api.ts) for HTTP requests such as:
- login / auth
- start analysis
- fetch session list
- fetch session details
- create annotations

Right now these are mocked. Replace them with real backend calls.

Example direction:

```ts
export async function fetchSessions(): Promise<SessionSummary[]> {
  const response = await fetch("http://localhost:8000/api/sessions");
  if (!response.ok) throw new Error("Failed to fetch sessions");
  return response.json();
}
```

### WebSocket Layer

Use [`services/socket.ts`](./services/socket.ts) for live streaming updates.

The intended backend endpoints are:

```ts
ws://localhost:8000/ws/frames
ws://localhost:8000/ws/cumulative
```

These sockets should send:
- current frame analysis results
- cumulative heatmap updates over time

Example expected frame payload:

```json
{
  "zones": [{ "row": 2, "col": 4, "score": 0.87 }],
  "type": "structural",
  "severity": 0.6
}
```

## Recommended Real Backend Flow

For a proper backend connection, use this flow:

1. User uploads a video or enters an RTSP stream on `/upload`
2. Frontend sends the request to the backend via `startAnalysis()`
3. Backend starts processing frames
4. Backend pushes live results over WebSocket
5. Frontend store updates the dashboard in real time
6. Operator annotations are sent back via REST API
7. Completed sessions are stored and returned by session APIs

## What to Replace for Production

### In `services/api.ts`

Replace:
- `mockAuthenticate`
- `startAnalysis`
- `fetchSessions`
- `fetchSessionDetail`
- `createAnnotation`

With:
- real `fetch()` calls to your backend
- auth token handling
- proper error handling
- environment-based API base URL

### In `services/socket.ts`

Replace mock timers with real `WebSocket` connections:

```ts
const socket = new WebSocket("ws://localhost:8000/ws/frames");

socket.onmessage = (event) => {
  const payload = JSON.parse(event.data);
  onMessage(payload);
};
```

### In the Dashboard UI

You can keep the same UI components.

Usually only these parts need to change:
- data source
- payload mapping
- loading/error states
- performance strategy if you move from DOM overlays to canvas

## State Management

The Zustand store in [`store/disaster-store.ts`](./store/disaster-store.ts) manages:
- auth state
- upload mode
- selected zone
- heatmap toggle
- filters
- live frame data
- cumulative heatmap data
- annotations
- session state

## Run Locally

Use:

```bash
npm install
npm run dev
```

If PowerShell blocks `npm`, use:

```bash
npm.cmd install
npm.cmd run dev
```

## Build

```bash
npm run build
```

## Current Status

- UI is production-style and frontend-complete
- backend integration is still mocked
- routing and build are working
- the current overlay approach is DOM-based, not canvas-based

## Next Recommended Steps

1. Add environment variables for API and WebSocket base URLs
2. Replace mock services with real backend calls
3. Standardize backend payloads for frames, zones, and sessions
4. Decide whether DOM overlays are enough or whether canvas is needed
5. Add auth integration for real SSO / invite flow

## Pipeline Architecture

```
Video Input (file or RTSP stream)
        │
        ▼
OpenCV Frame Ingestion
  └─ Every k-th frame (k ≈ 3–4) forwarded for inference
  └─ Skipped frames handled by ByteTrack interpolation
        │
        ▼
Image Queue (producer-consumer buffer)
        │
        ▼
YOLO11 Large Inference (GPU)
  └─ Fine-tuned on disaster aerial imagery
  └─ Outputs: bounding box, class, confidence per detection
  └─ Confidence threshold: 0.45
        │
        ├──────────────────────────────────────┐
        ▼                                      ▼
  Fire   Smoke   Heavy Structural   Flooded Zones   Collapsed Buildings
  (0.9)           Damage (0.6)       (0.7)           (1.0)
        │
        ▼
Spatial Grid Mapper (8×6 = 48 zones)
  └─ Maps each detection center to a grid cell
        │
        ▼
Impact Scorer
  └─ score(cell) += class_weight × confidence × persistence_factor
  └─ EMA decay (α = 0.92) applied every frame
        │
        ▼
Heatmap Renderer
  └─ Normalize → COLORMAP_JET → alpha blend onto frame
        │
        ▼
FastAPI WebSocket → React Dashboard
  └─ Live annotated video feed
  └─ Ranked zone score list
  └─ Cumulative session heatmap
```

---

## Detection Classes & Impact Weights

| Class | Description | Weight |
|---|---|---|
| `collapsed_building` | Rubble, broken rooflines, exposed interiors | 1.0 |
| `fire` | Active flame regions from aerial perspective | 0.9 |
| `flood` | Water coverage, submerged structures or roads | 0.7 |
| `heavy_damage` | Partially standing structures, significant damage | 0.6 |
| `debris` | Scattered material, blocked roads or zones | 0.3 |

---

## Scoring Logic

```
score(cell) += class_weight × confidence × persistence_factor

persistence_factor = min(1.0 + 0.05 × consecutive_frames, 2.0)
```

- **Persistence bonus** rewards damage detected consistently across multiple frames (real damage) over single-frame noise
- **EMA decay** (α = 0.92) ensures zones with no recent detections trend toward zero over ~12–15 frames
- **Confidence threshold** of 0.45 — detections below this are discarded before scoring
- **Persistence cap** at 2.0× prevents indefinite score inflation on static objects

---

## Configuration

All tunable parameters will live in `backend/config.py`:

---

## Tech Stack

| Layer | Technology |
|---|---|
| Object Detection | YOLO11 Large (Ultralytics) |
| Object Tracking | ByteTrack (built into Ultralytics) |
| Video I/O | OpenCV |
| Numerical Processing | NumPy |
| Heatmap Rendering | `cv2.applyColorMap` + `cv2.addWeighted` |
| Backend | FastAPI + WebSocket |
| Frontend | NextJS + HTML5 Canvas |
| Containerization | Docker + docker-compose |
| Multi-stream | Python `multiprocessing` |

---

## Datasets

DisasterVision is fine-tuned on a curated combination of four publicly available datasets, each targeting a specific disaster class. All datasets are used in **native YOLO format** (normalized bounding box `.txt` annotations) and unified under the project's class taxonomy before training.

---

### 1. Drone Flood Detection — Roboflow Universe
**Source:** [`ai-yolo-detection/drone-flood-detection-abdic-o5a73`](https://universe.roboflow.com/ai-yolo-detection/drone-flood-detection-abdic-o5a73)
**Format:** YOLOv8 object detection

This is the primary dataset for the `flood` class. Images are captured from a **drone/aerial perspective**, the same vantage point as the DisasterVision pipeline, making it the most geometrically relevant flood source in the stack. It covers flood water coverage over roads, submerged structures, and inundated zones as seen from above.

**Maps to:**
```
flood → flood (class 2)
```

---

### 2. Smoke & Fire Detection — Kaggle (D-Fire Dataset)
**Source:** [`sayedgamal99/smoke-fire-detection-yolo`](https://www.kaggle.com/datasets/sayedgamal99/smoke-fire-detection-yolo)
**Format:** YOLO (native, pre-split train/val/test)
**Size:** 21,527 annotated images

The D-Fire dataset is one of the largest and most widely benchmarked fire and smoke detection datasets available. It covers a wide range of real-world scenarios - outdoor/indoor, day/night, varying resolutions and lighting, annotated with bounding boxes for two classes: `fire` and `smoke`. Pre-split into training, validation, and test sets. Annotations are already in normalized YOLO format.

**Maps to:**
```
fire  → fire  (class 1)
smoke → smoke (class — see note below)
```

> **Note on smoke:** Depending on final class taxonomy, `smoke` may be kept as a standalone class or merged into `fire` with a lower impact weight. Smoke from a burning structure is a strong indirect indicator of active fire even when flames aren't visible from the aerial perspective.

---

### 3. Smoke & Fire Detection — Roboflow Universe
**Source:** [`yolov5-u5mjv/smoke-fire-wsde7`](https://universe.roboflow.com/yolov5-u5mjv/smoke-fire-wsde7)
**Format:** YOLOv5/v8 object detection

A supplementary fire and smoke dataset from Roboflow Universe used to increase annotation diversity for the `fire` and `smoke` classes. Combining this with the D-Fire dataset reduces the risk of the model overfitting to any single data distribution. Particularly useful for broadening coverage of scenarios underrepresented in D-Fire (e.g., industrial fire scenarios, dense smoke without visible flame).

**Maps to:**
```
fire  → fire  (class 1)
smoke → smoke / fire (class 1, depending on final taxonomy)
```

---

### 4. Flood Detection — Roboflow Universe
**Source:** [`long-nguyen-hoang-9ecmq/flood-4oe1x`](https://universe.roboflow.com/long-nguyen-hoang-9ecmq/flood-4oe1x)
**Format:** YOLOv8 object detection

A secondary flood dataset used alongside the drone flood dataset to increase total flood annotation count and scene variety. Provides additional coverage of flood scenarios from varied perspectives and geographies, helping the model generalize beyond the primary drone dataset's specific visual distribution.

**Maps to:**
```
flood → flood (class 2)
```

---

### Unified Class Taxonomy

All four datasets are merged under the following class mapping before fine-tuning:

| Class ID | Class Name | Source Datasets |
|---|---|---|
| 0 | `collapsed_building` | *(structural dataset — TBD / augmented from existing sources)* |
| 1 | `fire` | Kaggle D-Fire, Roboflow smoke-fire-wsde7 |
| 2 | `flood` | Roboflow drone-flood-abdic, Roboflow flood-4oe1x |
| 3 | `smoke` | Kaggle D-Fire, Roboflow smoke-fire-wsde7 |
| 4 | `heavy_damage` | *(structural dataset — TBD)* |

> **Structural damage classes** (`collapsed_building`, `heavy_damage`) are not covered by the four datasets above. These classes will be sourced from additional Roboflow Universe queries (search: `building damage detection`, `structural collapse aerial`) or augmented manually from available disaster imagery.

---

### Dataset Download

All Roboflow datasets can be downloaded directly via the Roboflow Python SDK:

```python
from roboflow import Roboflow

rf = Roboflow(api_key="YOUR_API_KEY")

# Drone flood dataset
project = rf.workspace("ai-yolo-detection").project("drone-flood-detection-abdic-o5a73")
dataset = project.version(1).download("yolov8")

# Supplementary flood dataset
project = rf.workspace("long-nguyen-hoang-9ecmq").project("flood-4oe1x")
dataset = project.version(1).download("yolov8")

# Fire & smoke (Roboflow)
project = rf.workspace("yolov5-u5mjv").project("smoke-fire-wsde7")
dataset = project.version(1).download("yolov8")
```

The Kaggle D-Fire dataset can be downloaded via:

```bash
kaggle datasets download -d sayedgamal99/smoke-fire-detection-yolo
unzip smoke-fire-detection-yolo.zip -d dataset/dfire/
```

---

### Annotation Format

All datasets use the standard YOLO bounding box format. Each image has a corresponding `.txt` file:

```
# class_id  cx  cy  width  height   (all normalized 0.0–1.0)
1  0.512  0.334  0.180  0.220    # fire
2  0.210  0.680  0.095  0.110    # flood
```

No format conversion is required for the Roboflow or Kaggle sources — they export directly in this structure.

## WebSocket API

The backend pushes two message types alternately to the frontend:

**Binary** — JPEG-encoded annotated frame, draw to `<canvas>`

**JSON** — Zone scores:
```json
{
  "zones": [
    { "row": 2, "col": 5, "score": 0.87 },
    { "row": 1, "col": 3, "score": 0.74 },
    ...
  ]
}
```

---

## Bonus: Multi-Stream Support

Each additional video stream runs as an independent Python `multiprocessing` worker with its own grid accumulator and scorer. A merger process aggregates score grids either side-by-side or as a combined spatial map for overlapping feeds.

```bash
# docker-compose.yml — add streams as additional services
stream1:
  environment:
    - VIDEO_SOURCE=rtsp://drone1/live
stream2:
  environment:
    - VIDEO_SOURCE=rtsp://drone2/live
```

---


## Team

Built for CodeReCET 2026 — CET Hackathon powered by Armada
