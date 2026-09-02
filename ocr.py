import easyocr

reader = easyocr.Reader(["en"])


def extract_text(image_path: str) -> tuple[str, float]:
    # Run EasyOCR on the photograph
    results = reader.readtext(image_path)

    if not results:
        return "", 0.0

    # Extract detected text
    texts = [text for _, text, _ in results]

    # Calculate average confidence
    confidences = [float(confidence) for _, _, confidence in results]
    average_confidence = sum(confidences) / len(confidences)

    # Combine all detected text into one string
    extracted_text = " ".join(texts)
    return extracted_text, average_confidence

"""def main():
    image_path = "dummy_label.jpg"

    text, confidence = extract_text(image_path)

    print("Extracted text:")
    print(text)

    print("\nAverage confidence:")
    print(round(confidence, 4))


if __name__ == "__main__":
    main()"""
