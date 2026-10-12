"""Detection-driven risk on a camera-frame grid (not a georeferenced map)."""
import cv2
import numpy as np

from config import EMA_DECAY, GRID_COLS, GRID_ROWS

SUPPORTED_CLASSES = ("fire", "smoke", "flood")


class GridScorer:
    def __init__(self):
        shape = (len(SUPPORTED_CLASSES), GRID_ROWS, GRID_COLS)
        self.current = np.zeros(shape, dtype=np.float64)
        self.total = np.zeros(shape, dtype=np.float64)
        self.persistence = np.zeros(shape, dtype=np.int32)
        self.samples = 0

    def update(self, detections, width, height):
        contribution = np.zeros_like(self.current)
        observed = np.zeros_like(self.persistence, dtype=bool)
        mapped = []
        for detection in detections:
            if detection.class_name not in SUPPORTED_CLASSES:
                continue
            x1, y1, x2, y2 = detection.box
            col = min(GRID_COLS - 1, max(0, int((x1 + x2) / 2 / width * GRID_COLS)))
            row = min(GRID_ROWS - 1, max(0, int((y1 + y2) / 2 / height * GRID_ROWS)))
            cls = SUPPORTED_CLASSES.index(detection.class_name)
            observed[cls, row, col] = True
            mapped.append((detection, cls, row, col))
        self.persistence = np.where(observed, self.persistence + 1, 0)
        for detection, cls, row, col in mapped:
            bonus = min(1 + 0.05 * self.persistence[cls, row, col], 2.0)
            contribution[cls, row, col] += detection.weight * detection.confidence * bonus
        self.current = EMA_DECAY * self.current + contribution
        self.total += contribution
        self.samples += 1
        return self.cells()

    def cells(self):
        result = []
        for row in range(GRID_ROWS):
            for col in range(GRID_COLS):
                raw = float(self.current[:, row, col].sum())
                mean = float(self.total[:, row, col].sum()) / max(1, self.samples)
                result.append({
                    "row": row, "col": col, "score": round(raw, 6),
                    "risk": round(raw / (1 + raw), 6),
                    "cumulativeRisk": round(mean / (1 + mean), 6),
                    "byClass": {
                        name: {
                            "score": round(float(self.current[index, row, col]), 6),
                            "mean": round(float(self.total[index, row, col]) / max(1, self.samples), 6),
                        } for index, name in enumerate(SUPPORTED_CLASSES)
                    },
                })
        return result


def render_heatmap(frame, cells, cumulative=False):
    key = "cumulativeRisk" if cumulative else "risk"
    grid = np.array([cell[key] for cell in cells], dtype=np.float32).reshape(GRID_ROWS, GRID_COLS)
    values = cv2.resize(grid, (frame.shape[1], frame.shape[0]), interpolation=cv2.INTER_LINEAR)
    colors = cv2.applyColorMap(np.uint8(np.clip(values * 255, 0, 255)), cv2.COLORMAP_JET)
    alpha = (values * 0.6)[..., None]
    return np.uint8(frame * (1 - alpha) + colors * alpha)
