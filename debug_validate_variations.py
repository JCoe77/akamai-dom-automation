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
        base_url = f"https://{config[section]['host']}"
        s = requests.Session()
        s.auth = EdgeGridAuth.from_edgerc(edgerc_path, section)
        return s, base_url
    except Exception as e:
        print(f"[ERROR] Error setting up authentication: {e}")
        sys.exit(1)

def debug_variations(domain, edgerc_path, section, account_switch_key=None):
    session, base_url = setup_authentication(edgerc_path, section)
    
    params = {}
    if account_switch_key:
        params['accountSwitchKey'] = account_switch_key
    
    payload = {
        "domains": [
            {
                "domainName": domain,
                "validationScope": "DOMAIN",
                "validationMethod": "DNS_TXT"
            }
        ]
    }

    # Variation 1: /domain-validation/v1/validate-requests (No /domains/ segment)
    endpoint_1 = "/domain-validation/v1/validate-requests"
    url_1 = urljoin(base_url, endpoint_1)
    print(f"\n[Test 1] POST {endpoint_1}")
    try:
        response = session.post(url_1, json=payload, params=params)
        print(f"Status: {response.status_code}")
        print(f"Body: {response.text[:300]}")
    except Exception as e: print(f"Error: {e}")

    # Variation 2: PUT /domain-validation/v1/domains/validate-requests (PUT method)
    endpoint_2 = "/domain-validation/v1/domains/validate-requests"
    url_2 = urljoin(base_url, endpoint_2)
    print(f"\n[Test 2] PUT {endpoint_2}")
    try:
        response = session.put(url_2, json=payload, params=params)
        print(f"Status: {response.status_code}")
        print(f"Body: {response.text[:300]}")
    except Exception as e: print(f"Error: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Debug Akamai Validate Requests Variations")
    parser.add_argument("domain", help="The domain to use")
    parser.add_argument("--edgerc", default=os.path.expanduser("~/.edgerc"), help="Path to .edgerc file")
    parser.add_argument("--section", default="default", help="Section in .edgerc to use")
    parser.add_argument("--ask", help="Optional Account Switch Key")
    
    args = parser.parse_args()
    debug_variations(args.domain, args.edgerc, args.section, args.ask)
