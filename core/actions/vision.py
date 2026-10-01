"""
Vision Action — Screen capture, OCR, and computer vision.
"""
from __future__ import annotations

import os

import base64
import io
from pathlib import Path

from core.action_registry import ActionResult, action, get_registry

# Optional imports
try:
    import mss
    MSS_AVAILABLE = True
except ImportError:
    MSS_AVAILABLE = False

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    import pytesseract
    TESSERACT_AVAILABLE = True
    try:
        _tess_exe = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        _tess_data = r"C:\Program Files\Tesseract-OCR\tessdata"
        if os.path.exists(_tess_exe):
            pytesseract.pytesseract.tesseract_cmd = _tess_exe
            _tess_data = r"C:\Program Files\Tesseract-OCR\tessdata"
            if os.path.isdir(_tess_data):
                os.environ["TESSDATA_PREFIX"] = _tess_data  # sistema tem valor errado; forca o certo
        if os.path.isdir(_tess_data):
            os.environ["TESSDATA_PREFIX"] = _tess_data  # sistema tem valor errado; forca o certo
    except Exception:
        pass
except ImportError:
    TESSERACT_AVAILABLE = False

try:
    import cv2
    import numpy as np
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False


@action(
    name="vision_screenshot",
    category="vision",
    description="Take a screenshot of the screen or region",
    parameters={
        "type": "object",
        "properties": {
            "region": {"type": "object", "description": "Region {left, top, width, height} (default: full screen)"},
            "path": {"type": "string", "description": "Save path (optional, returns base64 if not provided)"},
            "monitor": {"type": "integer", "description": "Monitor number (default: 0 for all)", "default": 0},
        },
        "required": [],
    },
)
def vision_screenshot_action(region: dict = None, path: str = "", monitor: int = 0) -> ActionResult:
    """Take a screenshot."""
    if not MSS_AVAILABLE:
        return ActionResult(success=False, error="mss not installed. Run: uv pip install mss")
    if not PIL_AVAILABLE:
        return ActionResult(success=False, error="PIL not installed. Run: uv pip install pillow")

    try:
        with mss.mss() as sct:
            if region:
                # Custom region
                monitor_dict = {
                    "left": region.get("left", 0),
                    "top": region.get("top", 0),
                    "width": region.get("width", 1920),
                    "height": region.get("height", 1080),
                }
            else:
                # Full screen or specific monitor
                monitors = sct.monitors
                if monitor < len(monitors):
                    monitor_dict = monitors[monitor]
                else:
                    monitor_dict = monitors[0]  # All monitors combined

            screenshot = sct.grab(monitor_dict)
            img = Image.frombytes("RGB", screenshot.size, screenshot.rgb)

            if path:
                save_path = Path(path).resolve()
                save_path.parent.mkdir(parents=True, exist_ok=True)
                img.save(save_path)
                return ActionResult(
                    success=True,
                    output=f"Screenshot saved to {save_path}",
                    data={"path": str(save_path), "size": img.size}
                )
            else:
                # Return base64
                buffered = io.BytesIO()
                img.save(buffered, format="PNG")
                b64 = base64.b64encode(buffered.getvalue()).decode()
                return ActionResult(
                    success=True,
                    output="Screenshot captured (base64)",
                    data={"screenshot_base64": b64, "size": img.size}
                )

    except Exception as e:
        return ActionResult(success=False, error=str(e))


@action(
    name="vision_ocr",
    category="vision",
    description="Extract text from image using OCR",
    parameters={
        "type": "object",
        "properties": {
            "image_path": {"type": "string", "description": "Path to image file"},
            "image_base64": {"type": "string", "description": "Base64 encoded image (alternative to path)"},
            "lang": {"type": "string", "description": "Language code (default: por+eng)", "default": "por+eng"},
        },
        "required": [],
    },
)
def vision_ocr_action(image_path: str = "", image_base64: str = "", lang: str = "por+eng") -> ActionResult:
    """Extract text from image using Tesseract OCR."""
    if not TESSERACT_AVAILABLE:
        return ActionResult(success=False, error="pytesseract not installed. Run: uv pip install pytesseract")
    if not PIL_AVAILABLE:
        return ActionResult(success=False, error="PIL not installed")

    try:
        if image_base64:
            img_data = base64.b64decode(image_base64)
            img = Image.open(io.BytesIO(img_data))
        elif image_path:
            img = Image.open(image_path)
        else:
            return ActionResult(success=False, error="Provide image_path or image_base64")

        # Convert to RGB if needed
        if img.mode != "RGB":
            img = img.convert("RGB")

        # OCR
        text = pytesseract.image_to_string(img, lang=lang)

        return ActionResult(
            success=True,
            output=text.strip(),
            data={"text": text.strip(), "lang": lang}
        )

    except Exception as e:
        return ActionResult(success=False, error=str(e))


@action(
    name="vision_find_template",
    category="vision",
    description="Find template image on screen (template matching)",
    parameters={
        "type": "object",
        "properties": {
            "template_path": {"type": "string", "description": "Path to template image"},
            "threshold": {"type": "number", "description": "Match threshold 0-1 (default: 0.8)", "default": 0.8},
            "region": {"type": "object", "description": "Search region {left, top, width, height}"},
        },
        "required": ["template_path"],
    },
)
def vision_find_template_action(template_path: str, threshold: float = 0.8, region: dict = None) -> ActionResult:
    """Find template on screen using OpenCV template matching."""
    if not OPENCV_AVAILABLE:
        return ActionResult(success=False, error="OpenCV not installed. Run: uv pip install opencv-python")
    if not MSS_AVAILABLE:
        return ActionResult(success=False, error="mss not installed")
    if not PIL_AVAILABLE:
        return ActionResult(success=False, error="PIL not installed")

    try:
        # Load template
        template = cv2.imread(template_path, cv2.IMREAD_COLOR)
        if template is None:
            return ActionResult(success=False, error=f"Template not found: {template_path}")

        h, w = template.shape[:2]

        # Take screenshot
        with mss.mss() as sct:
            if region:
                monitor_dict = {
                    "left": region.get("left", 0),
                    "top": region.get("top", 0),
                    "width": region.get("width", 1920),
                    "height": region.get("height", 1080),
                }
            else:
                monitor_dict = sct.monitors[0]

            screenshot = sct.grab(monitor_dict)
            img = Image.frombytes("RGB", screenshot.size, screenshot.rgb)
            screen = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

        # Template matching
        result = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
        locations = np.where(result >= threshold)

        matches = []
        for pt in zip(*locations[::-1], strict=False):  # x, y
            matches.append({
                "x": int(pt[0]),
                "y": int(pt[1]),
                "width": w,
                "height": h,
                "confidence": float(result[pt[1], pt[0]]),
            })

        return ActionResult(
            success=True,
            output=f"Found {len(matches)} matches",
            data={"matches": matches, "template_size": [w, h]}
        )

    except Exception as e:
        return ActionResult(success=False, error=str(e))


@action(
    name="vision_click_template",
    category="vision",
    description="Find and click template on screen",
    risk="MEDIUM",
    capability="PC_CONTROL",
    parameters={
        "type": "object",
        "properties": {
            "template_path": {"type": "string", "description": "Path to template image"},
            "threshold": {"type": "number", "description": "Match threshold 0-1 (default: 0.8)", "default": 0.8},
            "offset_x": {"type": "integer", "description": "X offset from match center (default: 0)", "default": 0},
            "offset_y": {"type": "integer", "description": "Y offset from match center (default: 0)", "default": 0},
        },
        "required": ["template_path"],
    },
)
def vision_click_template_action(template_path: str, threshold: float = 0.8, offset_x: int = 0, offset_y: int = 0) -> ActionResult:
    """Find template and click it."""
    from core.actions.computer_use import _foreground, computer_click_action
    observed = _foreground()
    if observed is None:
        return ActionResult(False, error='Janela ativa indisponível.', verificado=False)
    # First find
    result = vision_find_template_action(template_path, threshold)
    if not result.success:
        return result

    matches = result.data.get("matches", [])
    if not matches:
        return ActionResult(success=False, error="Template not found on screen")

    # Click first match
    match = matches[0]
    click_x = match["x"] + match["width"] // 2 + offset_x
    click_y = match["y"] + match["height"] // 2 + offset_y

    return computer_click_action(click_x, click_y, int(observed['hwnd']))


get_registry()
