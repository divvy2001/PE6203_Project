from pathlib import Path

import cv2


barcode_detector = cv2.barcode.BarcodeDetector()


def _decode_barcode(image):
    """Try to decode one barcode from an image or a preprocessed variant."""
    variants = [image]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    variants.extend(
        [
            cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC),
            cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1],
        ]
    )

    for variant in variants:
        try:
            decoded, _, _ = barcode_detector.detectAndDecode(variant)
        except cv2.error:
            continue
        if decoded and decoded.strip():
            return decoded.strip()

    return ""


def extract_text(image_path: str) -> tuple[str, float]:
    """Scan an image for a product barcode and return its value and confidence."""
    if not Path(image_path).exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    image = cv2.imread(image_path)
    if image is None:
        raise ValueError(f"Could not read image: {image_path}")

    barcode = _decode_barcode(image)
    return barcode, 1.0 if barcode else 0.0
