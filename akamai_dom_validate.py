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
        list: List of dictionaries [{'domain': 'example.com', 'scope': 'DOMAIN'}]
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
            
        # Default scope to DOMAIN for file inputs
        return [{'domain': d, 'scope': 'DOMAIN'} for d in domains]
    except Exception as e:
        print(f"[ERROR] Error reading Excel file: {e}")
        sys.exit(1)

def fetch_all_domains(session, base_url, account_switch_key=None):
    """
    Fetches all domains from the Akamai API using pagination.
    Returns:
        list: List of dictionaries [{'domain': 'example.com', 'scope': '...'}]
    """
    endpoint = "/domain-validation/v1/domains"
    url = urljoin(base_url, endpoint)
    
    domains_list = []
    page = 1
    page_size = 500 # Default/Max page size to minimize requests
    
    print("[INFO] Fetching all domains from Akamai API (Paginated)...")
    
    try:
        while True:
            params = {'page': page, 'pageSize': page_size}
            if account_switch_key:
                params['accountSwitchKey'] = account_switch_key
            
            print(f"[INFO] Fetching page {page}...")
            response = session.get(url, params=params)
            
            if response.status_code == 200:
                data = response.json()
                
                # Check if 'domains' key exists and has items
                current_batch = data.get('domains', [])
                if not current_batch:
                    break
                    
                for d in current_batch:
                    # Filter domains immediately.
                    # We ONLY want domains that are ready for validation (REQUEST_ACCEPTED, VALIDATION_IN_PROGRESS).
                    # This drastically reduces memory usage and processing time for large accounts.
                    d_status =  d.get('domainStatus', 'Unknown')
                    if d_status in ['REQUEST_ACCEPTED', 'VALIDATION_IN_PROGRESS']:
                        domains_list.append({
                            'domain': d.get('domainName'),
                            'scope': d.get('validationScope', 'DOMAIN'),
                            'status': d_status
                        })
                
                # If we received fewer items than page_size, we are on the last page
                if len(current_batch) < page_size:
                    break
                    
                page += 1
            else:
                print(f"[ERROR] Failed to fetch domains on page {page}: {response.status_code} - {response.text}")
                # We stop fetching here to avoid infinite loops or partial data issues
                break
                
        return domains_list
            
    except Exception as e:
        print(f"[ERROR] Exception fetching domains: {e}")
        sys.exit(1)

def check_validation_status(session, base_url, domain, scope='DOMAIN', account_switch_key=None):
    """
    Checks the current domain status via GET request.
    Returns:
        tuple: (Status_String (str), Domain_Status (str), Message (str))
    """
    endpoint = f"/domain-validation/v1/domains/{domain}"
    url = urljoin(base_url, endpoint)
    
    params = {'validationScope': scope}
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

def submit_validation_request(session, base_url, domain, scope='DOMAIN', account_switch_key=None):
    """
    Submits a validation request for the given domain.
    POST /domain-validation/v1/domains/validate-requests
    """
    endpoint = "/domain-validation/v1/domains/validate-now"
    url = urljoin(base_url, endpoint)

    params = {}
    if account_switch_key:
        params['accountSwitchKey'] = account_switch_key
    
    # Payload for validation request
    payload = {
        "domains": [
            {
                "domainName": domain,
                "validationScope": scope,
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

def process_domains(input_file, fetch_all, output_file, edgerc_path, section, account_switch_key=None, delay=0, limit=0):
    """
    Main processing function.
    """
    session, base_url = setup_authentication(edgerc_path, section)
    
    domain_entries = []
    
    if fetch_all:
        domain_entries = fetch_all_domains(session, base_url, account_switch_key)
        print(f"[INFO] Fetched {len(domain_entries)} domains from API.")
    elif input_file:
        print(f"[INFO] Reading domains from {input_file}...")
        domain_entries = read_domains(input_file)
        print(f"[INFO] Found {len(domain_entries)} domains.")
    else:
        print("[ERROR] No input provided. Use --all or provide an input file.")
        sys.exit(1)
    
    results = []
    submission_count = 0
    
    print("[INFO] Starting Validation Check & Submission...")
    if account_switch_key:
        print(f"[INFO] Using Account Switch Key: {account_switch_key}")
    if delay > 0:
        print(f"[INFO] Using delay of {delay} seconds between requests.")
    if limit > 0:
        print(f"[INFO] Submission limit set to: {limit}")

    try:
        for i, entry in enumerate(domain_entries):
            domain = entry['domain']
            scope = entry['scope']
            # Optimization: Use pre-fetched status if available
            domain_status = entry.get('status')
            
            # If status is unknown (e.g. from file input), fetch it
            if not domain_status or domain_status == 'Unknown':
                 _, domain_status, _ = check_validation_status(session, base_url, domain, scope, account_switch_key)

            # Logic: If REQUEST_ACCEPTED or VALIDATION_IN_PROGRESS -> Submit Validation
            # Filter condition
            if domain_status not in ['REQUEST_ACCEPTED', 'VALIDATION_IN_PROGRESS']:
                # Skip silently as requested
                continue

            print(f"[INFO] Processing {domain} (Scope: {scope})...")
            print(f"  -> Current Status: {domain_status}")

            # Check Limit
            if limit > 0 and submission_count >= limit:
                print(f"  -> Limit of {limit} reached. Skipping validation submission.")
                results.append({
                    "Domain": domain,
                    "Scope": scope,
                    "Previous Status": domain_status,
                    "Final Status": "Skipped (Limit Reached)",
                    "Message": "Skipped validation submission due to --limit."
                })
            else:
                print(f"  -> Triggering Validation Request...")
                new_status, post_msg = submit_validation_request(session, base_url, domain, scope, account_switch_key)
                print(f"  -> Result: {new_status}")
                
                if new_status not in ["Failed", "Exception"]: # Simple check, assumes non-error strings are success/attempts
                    submission_count += 1
                    
                results.append({
                    "Domain": domain,
                    "Scope": scope,
                    "Previous Status": domain_status,
                    "Final Status": new_status,
                    "Message": post_msg
                })
            
            # Add delay if specified, but not after the last item
            if delay > 0 and i < len(domain_entries) - 1:
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
    parser.add_argument("input_file", nargs='?', help="Path to the input Excel file containing domains (optional if --all is used)")
    parser.add_argument("--all", action="store_true", help="Fetch all domains from the API instead of using an input file")
    parser.add_argument("--output", "-o", default="validation_results.xlsx", help="Path to the output Excel file")
    parser.add_argument("--edgerc", "-e", default=os.path.expanduser("~/.edgerc"), help="Path to .edgerc file")
    parser.add_argument("--section", "-s", default="default", help="Section in .edgerc to use")
    parser.add_argument("--ask", help="Optional Account Switch Key")
    parser.add_argument("--delay", type=float, default=0, help="Optional delay in seconds")
    parser.add_argument("--limit", type=int, default=0, help="Optional limit on number of validation submissions")
    
    args = parser.parse_args()
    
    if not args.input_file and not args.all:
        parser.error("You must provide either an input_file or --all")
    
    process_domains(args.input_file, args.all, args.output, args.edgerc, args.section, args.ask, args.delay, args.limit)
