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

def debug_validate_requests(domain, edgerc_path, section, account_switch_key=None):
    session, base_url = setup_authentication(edgerc_path, section)
    
    params = {}
    if account_switch_key:
        params['accountSwitchKey'] = account_switch_key

    # Payload (same as before)
    payload = {
        "domains": [
            {
                "domainName": domain,
                "validationScope": "DOMAIN",
                "validationMethod": "DNS_TXT"
            }
        ]
    }

    # Test 1: POST /validate-requests + Application/JSON
    print(f"\n[Test 1] POST /domain-validation/v1/domains/validate-requests (Standard)")
    url = urljoin(base_url, "/domain-validation/v1/domains/validate-requests")
    try:
        response = session.post(url, json=payload, params=params)
        print(f"Status: {response.status_code}")
        print(f"Body: {response.text[:200]}")
    except Exception as e: print(f"Error: {e}")

    # Test 2: POST /validate-requests + Specific Content-Type
    print(f"\n[Test 2] POST /domain-validation/v1/domains/validate-requests (ContentType)")
    headers = {"Content-Type": "application/vnd.akamai.dv.v1+json"}
    try:
        # Note: requests json= will set application/json, so use data=json.dumps
        response = session.post(url, data=json.dumps(payload), headers=headers, params=params)
        print(f"Status: {response.status_code}")
        print(f"Body: {response.text[:200]}")
    except Exception as e: print(f"Error: {e}")

    # Test 3: POST /validate-now (Immediate validation)
    print(f"\n[Test 3] POST /domain-validation/v1/domains/validate-now")
    url_now = urljoin(base_url, "/domain-validation/v1/domains/validate-now")
    try:
        response = session.post(url_now, json=payload, params=params)
        print(f"Status: {response.status_code}")
        print(f"Body: {response.text[:200]}")
    except Exception as e: print(f"Error: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Debug Akamai Validate Requests Endpoint")
    parser.add_argument("domain", help="The domain to use in the payload")
    parser.add_argument("--edgerc", default=os.path.expanduser("~/.edgerc"), help="Path to .edgerc file")
    parser.add_argument("--section", default="default", help="Section in .edgerc to use")
    parser.add_argument("--ask", help="Optional Account Switch Key")
    
    args = parser.parse_args()
    
    debug_validate_requests(args.domain, args.edgerc, args.section, args.ask)
