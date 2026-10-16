"""Settings shared by detection, frame sampling and scoring."""
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
DATA_DIR = BASE_DIR / "data"
GRID_ROWS = 6
GRID_COLS = 8
EMA_DECAY = 0.92
DEFAULT_CONFIDENCE = 0.45
DEFAULT_FRAME_SKIP = 1
MAX_UPLOAD_BYTES = 500 * 1024 * 1024
MAX_FRAME_WIDTH = 960
