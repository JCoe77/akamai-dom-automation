import argparse
import requests
from akamai.edgegrid import EdgeGridAuth
from urllib.parse import urljoin
import os
import configparser
import json
import sys

def setup_authentication(edgerc_path, section):
    if not os.path.exists(edgerc_path):
        print(f"[ERROR] .edgerc file not found at {edgerc_path}")
        sys.exit(1)

    try:
        config = configparser.ConfigParser()
        config.read(edgerc_path)
        if section not in config:
             print(f"[ERROR] Section '{section}' not found in {edgerc_path}")
             sys.exit(1)
             
        base_url = f"https://{config[section]['host']}"
        s = requests.Session()
        s.auth = EdgeGridAuth.from_edgerc(edgerc_path, section)
        return s, base_url
    except Exception as e:
        print(f"[ERROR] Error setting up authentication: {e}")
        sys.exit(1)

def debug_validate(domain, edgerc_path, section, account_switch_key=None):
    session, base_url = setup_authentication(edgerc_path, section)
    
    print(f"--- Triggering Validation for Domain: {domain} ---")
    
    # POST /domain-validation/v1/domains/{domain}/validate
    endpoint = f"/domain-validation/v1/domains/{domain}/validate"
    url = urljoin(base_url, endpoint)

    params = {'validationScope': 'DOMAIN'}
    if account_switch_key:
        params['accountSwitchKey'] = account_switch_key
    
    # Should be empty payload per general pattern
    payload = {} 
    
    try:
        print(f"[INFO] Sending POST request to {endpoint}...")
        response = session.post(url, json=payload, params=params)
        
        print(f"\n[RESPONSE] Status Code: {response.status_code}")
        print(f"[RESPONSE] Headers: {dict(response.headers)}")
        try:
            print("[RESPONSE] Body JSON:")
            print(json.dumps(response.json(), indent=2))
        except:
            print("[RESPONSE] Body Text:")
            print(response.text)
            
    except Exception as e:
        print(f"[ERROR] API call failed: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Debug Akamai Domain Validation Endpoint")
    parser.add_argument("domain", help="The domain to trigger validation for")
    parser.add_argument("--edgerc", default=os.path.expanduser("~/.edgerc"), help="Path to .edgerc file")
    parser.add_argument("--section", default="default", help="Section in .edgerc to use")
    parser.add_argument("--ask", help="Optional Account Switch Key")
    
    args = parser.parse_args()
    
    debug_validate(args.domain, args.edgerc, args.section, args.ask)
