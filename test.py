from flask import Flask, request, jsonify
import pandas as pd
import requests
import traceback
from requests.auth import HTTPBasicAuth
import urllib3

app = Flask(__name__)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# === Hanshow API Config ===
API_BASE = "https://boolchand.slscanada.ca:9001"
USERNAME = "guest"
PASSWORD = "Z3Vlc3Q="
CUSTOMER_CODE = "boolchand"
STORE_CODE = "teststore"

# === Get token from Hanshow ===
def get_token():
    res = requests.post(f"{API_BASE}/proxy/token",
                        auth=HTTPBasicAuth(USERNAME, PASSWORD),
                        verify=False)
    res.raise_for_status()
    return res.json()["access_token"]

# === Build and send update payload ===
def update_esl(items):
    token = get_token()
    url = f"{API_BASE}/proxy/integration/{CUSTOMER_CODE}/{STORE_CODE}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    payload = {
        "customerStoreCode": CUSTOMER_CODE,
        "storeCode": STORE_CODE,
        "batchNo": "batch-a1-" + pd.Timestamp.now().strftime('%Y%m%d%H%M%S'),
        "items": items
    }
    response = requests.post(url, headers=headers, json=payload, verify=False)
    return response.status_code, response.json()

@app.route('/')
def home():
    return 'A1 ESL Updater is running'

@app.route('/convert', methods=['POST'])
def convert_excel():
    try:
        if 'file' not in request.files:
            return "No file uploaded", 400

        file = request.files['file']
        if file.filename == '':
            return "Empty filename", 400

        # Read and skip first row
        df = pd.read_excel(file, skiprows=1, dtype=str)

        items = []
        for _, row in df.iterrows():
            try:
                sku = str(row['Product ID']).strip()
                short_name = str(row['Product Code']).strip()
                price = float(row['Current Retail'])
                stock = int(float(row['Act On Hand'])) if 'Act On Hand' in row and pd.notna(row['Act On Hand']) else 0

                item = {
                    "IIS_COMMAND": "UPDATE",
                    "sku": sku,
                    "itemShortName": short_name,
                    "price1": price,
                    "inventory": stock
                }
                items.append(item)
            except Exception as row_error:
                print(f"❌ Skipping row due to error: {row_error}")

        if not items:
            return "No valid items found to update.", 400

        status, result = update_esl(items)
        return jsonify({
            "status": status,
            "result": result,
            "items_sent": len(items)
        })

    except Exception as e:
        print("=== ERROR IN /convert ===")
        print(str(e))
        traceback.print_exc()
        return f"Error: {str(e)}", 500

if __name__ == '__main__':
    app.run()
