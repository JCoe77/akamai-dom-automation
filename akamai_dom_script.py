import argparse
import pandas as pd
import requests
from akamai.edgegrid import EdgeGridAuth
from urllib.parse import urljoin
import os
import sys
import configparser
import time

def setup_authentication(edgerc_path, section):
    """
    Sets up the EdgeGrid authentication using the .edgerc file.
    """
    if not os.path.exists(edgerc_path):
        print(f"[ERROR] .edgerc file not found at {edgerc_path}")
        print("Please ensure you have created the .edgerc file with your Akamai API credentials.")
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

def read_domains(file_path):
    """
    Reads domains from an Excel file.
    Assumes the first column contains the domains, or looks for a 'Domain' or 'Hostname' header.
    Arguments:
        file_path (str): Path to the Excel file.
    Returns:
        list: List of domain strings, normalized to lowercase.
    """
    try:
        df = pd.read_excel(file_path)
        
        # logic to find the domain column and normalize
        # Normalization: lower() is critical to avoid API case-sensitivity issues
        if 'Domain' in df.columns:
            domains = df['Domain'].dropna().astype(str).str.strip().str.lower().tolist()
        elif 'Hostname' in df.columns:
            domains = df['Hostname'].dropna().astype(str).str.strip().str.lower().tolist()
        else:
            # Fallback to first column
            domains = df.iloc[:, 0].dropna().astype(str).str.strip().str.lower().tolist()
            
        return domains
    except Exception as e:
        print(f"[ERROR] Error reading Excel file: {e}")
        sys.exit(1)

def create_domain_validation(session, base_url, domain, account_switch_key=None):
    """
    Creates a DOMAIN scope validation for the given domain.
    Returns the token if successful, or None/Error message.
    """
    endpoint = "/domain-validation/v1/domains"
    url = urljoin(base_url, endpoint)

    # Prepare query parameters
    params = {}
    if account_switch_key:
        params['accountSwitchKey'] = account_switch_key
    
    # Payload for DOMAIN validation
    payload = {
        "domains": [
            {
                "domainName": domain,
                "validationScope": "DOMAIN"
            }
        ]
    }
    
    # Helper function to extract token from various response structures
    def find_token_in_data(data, target_domain):
        """
        Recursively searches for the validation token in the API response.
        Handles nested lists, 'successes', 'errors', and direct objects.
        """
        # Inner helper to check a specific item for the token or error status
        def check_item(item):
            # Ensure item is a dictionary before checking keys
            if not isinstance(item, dict):
                return None, None
                
            if item.get('domainName') == target_domain:
                # Check for "VALIDATED" status FIRST
                if item.get('status') == 'VALIDATED' or item.get('domainStatus') == 'VALIDATED':
                    return "Already Validated", "Already Validated"

                challenge = item.get('validationChallenge', {})
                if challenge:
                    # Success: Extract token from txtRecord value
                    txt_record = challenge.get('txtRecord', {})
                    if txt_record.get('value'):
                        return txt_record.get('name'), txt_record.get('value')
                
                if item.get('status') == 'Internal Server Error':
                    err = f"Error: {item.get('detail', 'Unknown Error')}"
                    return err, err
                
                # Check for "Domain already exists" error in 'detail' field
                if 'Domain already exists' in item.get('detail', ''):
                    return "Domain already exists", "Domain already exists"
            return None, None

        # Strategy 1: Check 'successes' list (common in 207 Multi-Status)
        if isinstance(data, dict) and 'successes' in data:
            for item in data['successes']:
                name, token = check_item(item)
                if token: return name, token

        # Strategy 2: Check 'errors' list
        if isinstance(data, dict) and 'errors' in data:
            for item in data['errors']:
                name, token = check_item(item) 
                if token: return name, token
        
        # Strategy 3: Check if data itself is a list of results
        if isinstance(data, list):
            for item in data:
                name, token = check_item(item)
                if token: return name, token
        
        # Strategy 4: Check if data is a single object (used in GET responses)
        name, token = check_item(data)
        if token: return name, token

        return None, None

    try:
        # POST request to create validation
        response = session.post(url, json=payload, params=params)
        
        if response.status_code in (200, 201, 207):
            data = response.json()
            name, token = find_token_in_data(data, domain)
            
            # If a token or specific status was found
            if token:
                # Fallback: if domain already exists, try fetching details via GET
                if "Domain already exists" in str(name):
                    print(f"[INFO] Domain exists. Fetching token via GET...")
                    return get_domain_details(session, base_url, domain, account_switch_key)
                return name, token
                
            return "Token not found", "Token not found"

        # Handle 409 Conflict (standard HTTP status for existing resource)
        elif response.status_code == 409:
             print(f"[INFO] Domain exists (409). Fetching token via GET...")
             return get_domain_details(session, base_url, domain, account_switch_key)

        else:
            print(f"[ERROR] Failed to create validation. Status: {response.status_code}")
            error_msg = f"Error: {response.status_code}"
            return error_msg, error_msg
            
    except Exception as e:
        print(f"[ERROR] API call failed: {e}")
        return f"Exception: {str(e)}", f"Exception: {str(e)}"

def get_domain_details(session, base_url, domain, account_switch_key=None):
    """
    Retrieves details for a specific domain to get the existing token.
    This is used as a fallback when the domain already exists.
    Arg:
        domain (str): The domain to query.
    Returns:
        tuple: (name, token)
    """
    endpoint = f"/domain-validation/v1/domains/{domain}"
    url = urljoin(base_url, endpoint)
    
    # Prepare query parameters
    params = {'validationScope': 'DOMAIN'}
    if account_switch_key:
        params['accountSwitchKey'] = account_switch_key

    try:
        # GET request must include validationScope='DOMAIN'
        response = session.get(url, params=params)
        
        if response.status_code == 200:
            data = response.json()
            
            # Check for "VALIDATED" status FIRST (supports both 'status' and 'domainStatus' fields)
            if data.get('status') == 'VALIDATED' or data.get('domainStatus') == 'VALIDATED':
                 return "Already Validated", "Already Validated"

            challenge = data.get('validationChallenge', {})
            if challenge:
                txt_record = challenge.get('txtRecord', {})
                if txt_record.get('value'):
                    return txt_record.get('name'), txt_record.get('value')
        
            return "Token not found", "Token not found"
        else:
            print(f"  [ERROR] Failed to get details. Status: {response.status_code}")
            return f"Error GET: {response.status_code}", f"Error GET: {response.status_code}"
            
    except Exception as e:
        print(f"  [ERROR] GET request failed: {e}")
        return f"Exception GET: {str(e)}", f"Exception GET: {str(e)}"

def process_domains(input_file, output_file, edgerc_path, section, account_switch_key=None, delay=0):
    """
    Main processing function.
    """
    print(f"[INFO] Reading domains from {input_file}...")
    domains = read_domains(input_file)
    print(f"[INFO] Found {len(domains)} domains.")
    
    session, base_url = setup_authentication(edgerc_path, section)
    
    results = []
    
    print("[INFO] Starting API calls...")
    if account_switch_key:
        print(f"[INFO] Using Account Switch Key: {account_switch_key}")
    if delay > 0:
        print(f"[INFO] Using delay of {delay} seconds between requests.")

    try:
        for i, domain in enumerate(domains):
            print(f"[INFO] Processing {domain}...")
            name, token = create_domain_validation(session, base_url, domain, account_switch_key)
            results.append({
                "Domain": domain,
                "Name": name,
                "Token": token
            })
            
            # Add delay if specified, but not after the last item
            if delay > 0 and i < len(domains) - 1:
                time.sleep(delay)

    except KeyboardInterrupt:
        print("\n[WARN] Script interrupted by user! Saving progress...")
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}. Saving progress...")
    finally:
        # Safety Save: Ensure results are written even if interrupted
        print(f"[INFO] Writing results to {output_file}...")
        try:
            if results:
                results_df = pd.DataFrame(results)
                # Ensure column order
                results_df = results_df[['Domain', 'Name', 'Token']]
                results_df.to_excel(output_file, index=False)
                print("[INFO] Done.")
            else:
                print("[WARN] No results to write.")
        except Exception as e:
            print(f"[ERROR] Error writing output file: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Akamai Domain Ownership Manager Script")
    parser.add_argument("input_file", help="Path to the input Excel file containing domains")
    parser.add_argument("--output", "-o", default="results.xlsx", help="Path to the output Excel file (default: results.xlsx)")
    parser.add_argument("--edgerc", "-e", default=os.path.expanduser("~/.edgerc"), help="Path to .edgerc file (default: ~/.edgerc)")
    parser.add_argument("--section", "-s", default="default", help="Section in .edgerc to use (default: default)")
    parser.add_argument("--ask", help="Optional Account Switch Key (accountSwitchKey) to include in API calls")
    parser.add_argument("--delay", type=float, default=0, help="Optional delay in seconds between API calls to avoid rate limits (default: 0)")
    
    args = parser.parse_args()
    
    process_domains(args.input_file, args.output, args.edgerc, args.section, args.ask, args.delay)
