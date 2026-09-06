# PE6203_Project
I added:
requirements.txt
Lists all the Python packages the app needs (Streamlit, Pinecone, etc.) so Render knows what to install.

chain.py
Takes a barcode, looks up the product (Pinecone or OpenFoodFacts), applies a fixed rule to decide ok/care/avoid, then asks the AI to explain it.

app_latest.py
New frontend for the barcode version — scan/enter a barcode instead of reviewing ingredient text. Might still need UI polish, but the logic behind it works.
<<<< If it works, it works 😄🤷 >>>>
