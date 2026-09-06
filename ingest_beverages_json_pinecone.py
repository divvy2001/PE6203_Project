"""Embed beverages.json products and upsert them into the Pinecone product index."""

import json
import os
import time
from decimal import Decimal
from pathlib import Path

import ijson
from dotenv import load_dotenv
from openai import OpenAI, RateLimitError
from pinecone import Pinecone, ServerlessSpec

load_dotenv()

SOURCE = Path("beverages.json")
PRODUCT_INDEX_NAME = os.getenv("PINECONE_PRODUCT_INDEX", "ingrid-beverages")
EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_DIMENSION = 1536
BATCH_SIZE = 100
MAX_RETRIES = 5

# Nutrient keys pulled from OpenFoodFacts' "_100g" nutriment fields.
NUTRIENT_KEYS = [
    "energy-kcal", "energy-kj", "fat", "saturated-fat", "carbohydrates",
    "sugars", "added-sugars", "fiber", "proteins", "salt", "sodium",
]


def get_openai_client():
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is not set.")
    return OpenAI(api_key=api_key)


def get_pinecone_index():
    api_key = os.getenv("PINECONE_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("PINECONE_API_KEY is not set.")

    pc = Pinecone(api_key=api_key)
    if PRODUCT_INDEX_NAME not in [index.name for index in pc.list_indexes()]:
        pc.create_index(
            name=PRODUCT_INDEX_NAME,
            dimension=EMBEDDING_DIMENSION,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )
    return pc.Index(PRODUCT_INDEX_NAME)


def build_nutrition_rows(nutriments):
    """Extract the per-100g nutrient rows used by chain.py's nutrition parser."""
    nutriments = nutriments or {}
    rows = []
    for key in NUTRIENT_KEYS:
        value = nutriments.get(f"{key}_100g")
        if value is None:
            continue
        rows.append({"name": key, "100g": value, "unit": nutriments.get(f"{key}_unit", "")})
    return rows


def build_embedding_text(product, nutrition_rows):
    """Compose the descriptive text stored/embedded for a product, matching chain.py's parser."""
    lines = [
        f"Product: {product.get('product_name') or 'Unknown product'}",
        f"Brand: {product.get('brands') or 'Unknown brand'}",
        f"Categories: {', '.join(product.get('categories_tags') or [])}",
        f"Ingredients: {product.get('ingredients_text') or 'Not provided'}",
        f"Nutrition per 100g: {json.dumps(nutrition_rows, ensure_ascii=False, default=str)}",
        f"Nutri-Score: {product.get('nutriscore_grade') or 'unknown'}",
    ]
    return "\n".join(lines)


def build_metadata(product, text):
    return {
        "product_name": product.get("product_name") or "",
        "product_name_en": product.get("product_name") or "",
        "brands": product.get("brands") or "",
        "ingredients_text": product.get("ingredients_text") or "",
        "ingredients_text_en": product.get("ingredients_text") or "",
        "ingredients_tags": ";".join(product.get("ingredients_tags") or []),
        "categories_tags": ";".join(product.get("categories_tags") or []),
        "nutriscore_grade": product.get("nutriscore_grade") or "",
        "nova_group": product.get("nova_group") or "",
        "quantity": product.get("quantity") or "",
        "text": text,
    }


def embed_with_retry(client, texts):
    """Request embeddings, retrying with backoff on rate limits."""
    for attempt in range(MAX_RETRIES):
        try:
            response = client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
            return [item.embedding for item in response.data]
        except RateLimitError:
            wait_seconds = 2 ** attempt
            print(f"Rate limited, retrying in {wait_seconds}s...", flush=True)
            time.sleep(wait_seconds)
    raise RuntimeError("Exceeded retries while requesting embeddings.")


def iter_products(source):
    with source.open("rb") as handle:
        yield from ijson.items(handle, "item")


def main():
    if not SOURCE.exists():
        raise SystemExit(f"{SOURCE} not found. Run filter_beverages_parquet.py first.")

    client = get_openai_client()
    index = get_pinecone_index()

    batch_ids, batch_texts, batch_metadata = [], [], []
    ingested, skipped = 0, 0

    def flush_batch():
        nonlocal batch_ids, batch_texts, batch_metadata, ingested
        if not batch_ids:
            return
        embeddings = embed_with_retry(client, batch_texts)
        vectors = [
            {"id": pid, "values": vector, "metadata": meta}
            for pid, vector, meta in zip(batch_ids, embeddings, batch_metadata)
        ]
        index.upsert(vectors=vectors)
        ingested += len(vectors)
        print(f"Ingested {ingested} products so far...", flush=True)
        batch_ids, batch_texts, batch_metadata = [], [], []

    for product in iter_products(SOURCE):
        barcode = str(product.get("code") or "").strip()
        if not barcode.isdigit():
            skipped += 1
            continue

        nutrition_rows = build_nutrition_rows(product.get("nutriments"))
        text = build_embedding_text(product, nutrition_rows)
        metadata = build_metadata(product, text)

        batch_ids.append(barcode)
        batch_texts.append(text)
        batch_metadata.append(metadata)

        if len(batch_ids) >= BATCH_SIZE:
            flush_batch()

    flush_batch()
    print(f"Done. Ingested {ingested} products, skipped {skipped} without a valid barcode.")


if __name__ == "__main__":
    main()
