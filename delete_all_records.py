import os
import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

# Load credentials from your existing .env file
load_dotenv()

BASE_URL = os.getenv("FUSION_BASE_URL")
USERNAME = os.getenv("FUSION_USERNAME")
PASSWORD = os.getenv("FUSION_PASSWORD")

CUSTOM_OBJECT_URL = f"{BASE_URL.rstrip('/')}/fscmRestApi/resources/11.13.18.05/Inspira_Einvoice_c"
AUTH = HTTPBasicAuth(USERNAME, PASSWORD)
HEADERS = {"Accept": "application/json"}

def delete_all_records():
    print(f"Connecting to Oracle Fusion to purge records...")
    
    total_deleted = 0
    while True:
        try:
            # Oracle paginates at 25 records per request. We loop until the object is empty.
            response = requests.get(CUSTOM_OBJECT_URL, auth=AUTH, headers=HEADERS)
            response.raise_for_status()
            items = response.json().get("items", [])
            
            if not items:
                print(f"--- Cleanup Complete! Total records deleted: {total_deleted} ---")
                break
                
            for item in items:
                record_id = item.get("Id")
                trx_number = item.get("Trx_Number_c", "Unknown")
                delete_url = f"{CUSTOM_OBJECT_URL}/{record_id}"
                
                del_resp = requests.delete(delete_url, auth=AUTH)
                del_resp.raise_for_status()
                print(f"Deleted Record ID: {record_id} | Trx_Number: {trx_number}")
                total_deleted += 1
                
        except requests.exceptions.RequestException as e:
            print(f"Error during deletion process: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Error Details: {e.response.text}")
            break

if __name__ == "__main__":
    delete_all_records()