"""Export OpenFoodFacts beverage products from food.parquet to beverages.json."""

import json
from pathlib import Path

import pyarrow.parquet as pq

SOURCE = Path("food.parquet")
OUTPUT = Path("beverages.json")
CATEGORY_TAG = "en:beverages"
FIELDS = [
    "code",
    "product_name",
    "brands",
    "generic_name",
    "ingredients_text",
    "ingredients_tags",
    "categories_tags",
    "countries_tags",
    "nutriments",
    "nutriscore_grade",
    "nutriscore_score",
    "nova_group",
    "nutrient_levels",
    "labels_tags",
    "allergens_tags",
    "traces_tags",
    "quantity",
    "serving_size",
    "packaging",
    "completeness",
]


def is_beverage(row):
    categories = row.get("categories_tags") or []
    return CATEGORY_TAG in categories


def main():
    parquet = pq.ParquetFile(SOURCE)
    exported = 0
    scanned = 0
    temporary = OUTPUT.with_suffix(".json.part")

    with temporary.open("w", encoding="utf-8") as output:
        output.write("[\n")
        first = True
        for batch in parquet.iter_batches(batch_size=512, columns=FIELDS):
            for row in batch.to_pylist():
                scanned += 1
                if not is_beverage(row):
                    continue
                if not row.get("code"):
                    continue
                if not first:
                    output.write(",\n")
                json.dump(row, output, ensure_ascii=False, separators=(",", ":"))
                first = False
                exported += 1
            if scanned % 100000 < 512:
                print(f"Scanned {scanned} rows; exported {exported} beverages", flush=True)
        output.write("\n]\n")

    temporary.replace(OUTPUT)
    print(f"Wrote {exported} beverages to {OUTPUT}")


if __name__ == "__main__":
    main()
