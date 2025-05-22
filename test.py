from flask import Flask, request, jsonify
import pandas as pd
import requests
import traceback
from requests.auth import HTTPBasicAuth
import urllib3

app = Flask(__name__)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# === Hanshow API Configuration ===
API_BASE = "https://boolchand.slscanada.ca:9001"
USERNAME = "guest"
PASSWORD = "Z3Vlc3Q="
CUSTOMER_CODE = "boolchand"
STORE_CODE = "teststore"

# === Get bearer token from Hanshow ===
def get_token():
    response = requests.post(
        f"{API_BASE}/proxy/token",
        auth=HTTPBasicAuth(USERNAME, PASSWORD),
        verify=False
    )
    response.raise_for_status()
    return response.json()["access_token"]

# === Send items in batches of 1000 ===
def update_esl(items):
    token = get_token()
    url = f"{API_BASE}/proxy/integration/{CUSTOMER_CODE}/{STORE_CODE}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    responses = []
    batch_size = 1000
    for i in range(0, len(items), batch_size):
        batch = items[i:i+batch_size]
        payload = {
            "customerStoreCode": CUSTOMER_CODE,
            "storeCode": STORE_CODE,
            "batchNo": f"batch-{pd.Timestamp.now().strftime('%Y%m%d%H%M%S')}-{i//batch_size + 1}",
            "items": batch
        }

        print(f"📦 Sending batch {i//batch_size + 1} with {len(batch)} items")
        response = requests.post(url, headers=headers, json=payload, verify=False)
        print("📡 API Response:", response.status_code, response.text)
        try:
            res_json = response.json()
        except:
            res_json = {"error": "Failed to decode JSON", "text": response.text}
        responses.append({
            "batch": i//batch_size + 1,
            "status": response.status_code,
            "response": res_json
        })

    return 200, {"batches_sent": len(responses), "results": responses}

@app.route('/')
def home():
    return '✅ ESL Update Service is Running'

@app.route('/convert', methods=['POST'])
def convert_excel():
    try:
        if 'file' not in request.files:
            return "No file uploaded", 400

        file = request.files['file']
        if file.filename == '':
            return "Empty filename", 400

        df = pd.read_excel(file, skiprows=1, dtype=str)
        print("🧾 Columns in uploaded Excel:", df.columns.tolist())

        items = []
        for _, row in df.iterrows():
            try:
                sku = str(row['Product ID']).strip()
                short_name = str(row['Product Code']).strip()
                name = str(row['Description']).strip()
                brand = str(row['Brand Name']).strip()
                retail = float(row['Current Retail'])

                # === PRICE CALCULATIONS ===
                price1 = round(retail * 1.0753, 2)     # with tax
                price2 = round(price1 / 1.8, 2)         # in dollars

                # === STOCK ===
                stock_column = next(
                    (col for col in row.index if col.strip().lower().replace(" ", "") in [
                        "qtyonhand", "quantityonhand", "onhand", "stock"
                    ]),
                    None
                )
                stock = int(float(row[stock_column])) if stock_column and pd.notna(row[stock_column]) else 0

                item = {
                    "IIS_COMMAND": "UPDATE",
                    "sku": sku,
                    "itemShortName": short_name,
                    "itemName": name,
                    "manufacturer": brand,
                    "price1": price1,
                    "price2": price2,
                    "inventory": stock
                }

                items.append(item)
            except Exception as row_error:
                print(f"⚠️ Skipping row: {row_error}")

        if not items:
            return "No valid items found.", 400

        status, result = update_esl(items)
        return jsonify({
            "status": status,
            "total_items": len(items),
            "result": result
        })

    except Exception as e:
        print("❌ ERROR IN /convert")
        traceback.print_exc()
        return f"Error: {str(e)}", 500

if __name__ == '__main__':
    app.run()
