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

def check_validation_status(session, base_url, domain, account_switch_key=None):
    """
    Checks the current domain status via GET request.
    Returns:
        tuple: (Status_String (str), Domain_Status (str), Message (str))
    """
    endpoint = f"/domain-validation/v1/domains/{domain}"
    url = urljoin(base_url, endpoint)
    
    params = {'validationScope': 'DOMAIN'}
    if account_switch_key:
        params['accountSwitchKey'] = account_switch_key

    try:
        response = session.get(url, params=params)
        
        if response.status_code == 200:
            data = response.json()
            status = data.get('status', 'Unknown')
            domain_status = data.get('domainStatus', 'Unknown')
            return status, domain_status, "Status retrieved successfully."
            
        elif response.status_code == 404:
            return "Not Found", "Not Found", "Domain does not exist."
        else:
            return f"Error ({response.status_code})", f"Error ({response.status_code})", f"GET failed with status {response.status_code}"
            
    except Exception as e:
        return "Exception", "Exception", f"GET Exception: {str(e)}"

def submit_validation_request(session, base_url, domain, account_switch_key=None):
    """
    Submits a validation request for the given domain.
    POST /domain-validation/v1/domains/validate-now
    """
    endpoint = "/domain-validation/v1/domains/validate-now"
    url = urljoin(base_url, endpoint)

    params = {}
    if account_switch_key:
        params['accountSwitchKey'] = account_switch_key
    
    # Payload for validate-now
    payload = {
        "domains": [
            {
                "domainName": domain,
                "validationScope": "DOMAIN",
                "validationMethod": "DNS_TXT"
            }
        ]
    }
    
    try:
        response = session.post(url, json=payload, params=params)
        
        if response.status_code in (200, 201, 202, 207):
             # Try to parse the domainStatus from the response
             try:
                 data = response.json()
                 # Handle simple response or list response
                 if isinstance(data, dict):
                     if 'domains' in data:
                         for d in data['domains']:
                             if d.get('domainName') == domain:
                                 return d.get('domainStatus', 'Submitted'), "Validation request submitted."
                     # Fallback check
                     return data.get('domainStatus', 'Submitted'), "Validation request submitted."
             except:
                 pass
             return "Submitted", "Validation request submitted (Status 2xx)."
        
        elif response.status_code == 400:
             return "Failed (400)", f"Client Error: {response.text}"
        else:
             return f"Failed ({response.status_code})", f"API Error: {response.status_code}"

    except Exception as e:
        return "Exception", f"POST Exception: {str(e)}"

def process_domains(input_file, output_file, edgerc_path, section, account_switch_key=None, delay=0):
    """
    Main processing function.
    """
    print(f"[INFO] Reading domains from {input_file}...")
    domains = read_domains(input_file)
    print(f"[INFO] Found {len(domains)} domains.")
    
    session, base_url = setup_authentication(edgerc_path, section)
    
    results = []
    
    print("[INFO] Starting Validation Check & Submission...")
    if account_switch_key:
        print(f"[INFO] Using Account Switch Key: {account_switch_key}")
    if delay > 0:
        print(f"[INFO] Using delay of {delay} seconds between requests.")

    try:
        for i, domain in enumerate(domains):
            print(f"[INFO] Processing {domain}...")
            
            # 1. GET Check
            status, domain_status, msg = check_validation_status(session, base_url, domain, account_switch_key)
            print(f"  -> Current Status: {domain_status}")
            
            # Logic: If REQUEST_ACCEPTED or VALIDATION_IN_PROGRESS -> Submit Validation
            if domain_status in ['REQUEST_ACCEPTED', 'VALIDATION_IN_PROGRESS']:
                print(f"  -> Triggering Validation Request...")
                new_status, post_msg = submit_validation_request(session, base_url, domain, account_switch_key)
                print(f"  -> Result: {new_status}")
                results.append({
                    "Domain": domain,
                    "Previous Status": domain_status,
                    "Final Status": new_status,
                    "Message": post_msg
                })
            else:
                print(f"  -> Skipping (Status not ready for validation).")
                results.append({
                    "Domain": domain,
                    "Previous Status": domain_status,
                    "Final Status": "Skipped",
                    "Message": f"Skipped because status is {domain_status}."
                })
            
            # Add delay if specified, but not after the last item
            if delay > 0 and i < len(domains) - 1:
                time.sleep(delay)

    except KeyboardInterrupt:
        print("\n[WARN] Script interrupted by user! Saving progress...")
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}. Saving progress...")
    finally:
        # Safety Save
        print(f"[INFO] Writing results to {output_file}...")
        try:
            if results:
                results_df = pd.DataFrame(results)
                # Reorder if desired, but default is fine
                results_df.to_excel(output_file, index=False)
                print("[INFO] Done.")
            else:
                print("[WARN] No results to write.")
        except Exception as e:
            print(f"[ERROR] Error writing output file: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Akamai Domain Validation Trigger Script")
    parser.add_argument("input_file", help="Path to the input Excel file containing domains")
    parser.add_argument("--output", "-o", default="validation_results.xlsx", help="Path to the output Excel file")
    parser.add_argument("--edgerc", "-e", default=os.path.expanduser("~/.edgerc"), help="Path to .edgerc file")
    parser.add_argument("--section", "-s", default="default", help="Section in .edgerc to use")
    parser.add_argument("--ask", help="Optional Account Switch Key")
    parser.add_argument("--delay", type=float, default=0, help="Optional delay in seconds")
    
    args = parser.parse_args()
    
    process_domains(args.input_file, args.output, args.edgerc, args.section, args.ask, args.delay)
