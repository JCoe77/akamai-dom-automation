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
    Reads domains and validationScope from an Excel file.
    """
    try:
        df = pd.read_excel(file_path)
        
        # Normalize column names for flexible matching
        df.columns = df.columns.astype(str).str.strip()
        
        # Identify Domain Column
        domain_col_name = None
        for col in df.columns:
            if col.lower() in ['domain', 'hostname', 'domainname', 'domain name']:
                domain_col_name = col
                break
        
        # Fallback to first column if not found
        if not domain_col_name:
            domain_col_name = df.columns[0]
            print(f"[WARN] Could not identify 'Domain' column. Using first column '{domain_col_name}' as domain.")

        # Identify Scope Column
        scope_col_name = None
        for col in df.columns:
            if col.lower() in ['validationscope', 'scope', 'validation scope']:
                scope_col_name = col
                break
        
        if not scope_col_name:
             print(f"[WARN] 'Scope' column not found in {file_path}. Defaulting all to 'DOMAIN'.")

        targets = []
        for index, row in df.iterrows():
            d = row[domain_col_name]
            s = row[scope_col_name] if scope_col_name else "DOMAIN"
            
            # Simple validation
            if pd.isna(d) or str(d).strip() == '':
                continue
                
            d_str = str(d).strip().lower()
            # Force uppercase for scope as API enums are usually uppercase (e.g. DOMAIN)
            s_str = str(s).strip().upper() if not pd.isna(s) else "DOMAIN" 
            
            # Validate Scope value
            if s_str not in ['DOMAIN', 'M_HOST', 'S_HOST']: # Add others if known, but these are standard
                 # Warning or default? Let's just keep it. API will error if invalid.
                 pass

            targets.append({
                "domainName": d_str,
                "validationScope": s_str
            })
            
        print(f"[INFO] Loaded {len(targets)} domains for validation from {file_path}")
        return targets

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

def bulk_submit_validation(session, base_url, domains_batch, account_switch_key=None):
    """
    Submits a validation request for a batch of domains.
    POST /domain-validation/v1/domains/validate-requests (or validate-now)
    
    Handles 400 Bad Request errors by:
    1. Parsing the 'errors' list to identify specific invalid domains.
    2. Failing those specific domains.
    3. Retrying the rest.
    """
    # Using the validate-now endpoint based on existing script. 
    # User mentioned "validate-requests" in their prompt but the link was generic.
    # The payload structure { "domains": [...] } is compatible with the bulk endpoints.
    endpoint = "/domain-validation/v1/domains/validate-now"
    url = urljoin(base_url, endpoint)

    params = {}
    if account_switch_key:
        params['accountSwitchKey'] = account_switch_key
    
    # Construct Payload
    # The API expects: { "domains": [ { "domainName": "...", "validationScope": "..." }, ... ] }
    # Our domains_batch already has these keys (from read_domains)
    # We just need to ensure validationMethod is added if required, or defaults are fine.
    # The previous script added "validationMethod": "DNS_TXT". We should probably keep that.
    
    payload_domains = []
    for d in domains_batch:
        payload_domains.append({
            "domainName": d['domainName'],
            "validationScope": d['validationScope'],
            "validationMethod": "DNS_TXT" # Enforce DNS_TXT as per previous script
        })

    # Construct Payload
    payload = {
        "domains": payload_domains
    }
    
    results = []
    
    try:
        response = session.post(url, json=payload, params=params)
        status_code = response.status_code
        
        if status_code == 400:
             print(f"[WARN] Batch failed with 400. Parsing errors...")
             try:
                 error_data = response.json()
                 errors_list = error_data.get('errors', [])
                 
                 bad_indices = set()
                 for err in errors_list:
                     field = err.get('field', '')
                     # Example: domains[0].domainName
                     if field.startswith('domains[') and ']' in field:
                         try:
                             idx = int(field.split('[')[1].split(']')[0])
                             bad_indices.add(idx)
                         except:
                             pass
                 
                 if not bad_indices:
                     # Fail all if we can't pinpoint
                     for d in domains_batch:
                         results.append({
                             "Domain": d['domainName'],
                             "Scope": d['validationScope'],
                             "Status Code": status_code,
                             "Result": "Failed",
                             "Error Title": error_data.get('title'),
                             "Error Detail": error_data.get('detail'),
                             "Details": f"Batch Error: {error_data.get('detail', 'Unknown Error')}"
                         })
                 else:
                     retry_batch = []
                     
                     for i, d in enumerate(domains_batch):
                         if i in bad_indices:
                             # Find specific error
                             specific_title = "Invalid Request"
                             specific_detail = "Invalid Request"
                             
                             for err in errors_list:
                                 if f"domains[{i}]" in err.get('field', ''):
                                     specific_title = err.get('title', specific_title)
                                     specific_detail = err.get('detail', specific_detail)
                                     break
                             
                             results.append({
                                 "Domain": d['domainName'],
                                 "Scope": d['validationScope'],
                                 "Status Code": status_code,
                                 "Result": "Failed",
                                 "Error Title": specific_title,
                                 "Error Detail": specific_detail
                             })
                         else:
                             retry_batch.append(d)
                     
                     if retry_batch:
                         print(f"[INFO] Retrying {len(retry_batch)} valid domains...")
                         retry_results = bulk_submit_validation(session, base_url, retry_batch, account_switch_key)
                         results.extend(retry_results)
                         
             except Exception as e:
                 print(f"[ERROR] Error parsing 400 response: {e}")
                 for d in domains_batch:
                     results.append({
                             "Domain": d['domainName'],
                             "Scope": d['validationScope'],
                             "Status Code": status_code,
                             "Result": "Failed",
                             "Error Detail": f"Exception during retry logic: {e}"
                         })

        elif status_code in (200, 202):
            # Success - Request processed
            # Parse response to get individual domain statuses
            try:
                response_data = response.json()
                resp_domains = response_data.get('domains', [])
                
                # Create a lookup for quick access: (domain, scope) -> status
                # If scope is missing in response, fallback to just domain name
                status_map = {}
                for rd in resp_domains:
                    d_name = rd.get('domainName')
                    d_scope = rd.get('validationScope') # Might be None in response
                    d_status = rd.get('domainStatus', 'Submitted')
                    
                    if d_name:
                        if d_scope:
                            status_map[(d_name, d_scope)] = d_status
                        # Also map just by name as fallback
                        if d_name not in status_map:
                            status_map[d_name] = d_status
                            
                for d in domains_batch:
                    # Try exact match first
                    status = status_map.get((d['domainName'], d['validationScope']))
                    if not status:
                        # Fallback to name only
                        status = status_map.get(d['domainName'], "Submitted")
                        
                    results.append({
                        "Domain": d['domainName'],
                        "Scope": d['validationScope'],
                        "Status Code": status_code,
                        "Result": "Submitted",
                        "Details": f"Status: {status}",
                        "Error Title": "",
                        "Error Detail": ""
                    })
                    
            except Exception as e:
                # If JSON parse fails but status was 200, log as success but warn
                print(f"[WARN] Failed to parse 200 response JSON: {e}")
                for d in domains_batch:
                    results.append({
                        "Domain": d['domainName'],
                        "Scope": d['validationScope'],
                        "Status Code": status_code,
                        "Result": "Submitted",
                        "Details": "Request accepted (Response parsing failed)",
                        "Error Title": "",
                        "Error Detail": ""
                    })
        else:
             # Other errors
             for d in domains_batch:
                 results.append({
                     "Domain": d['domainName'],
                     "Scope": d['validationScope'],
                     "Status Code": status_code,
                     "Result": "Error",
                     "Details": response.text
                 })

    except Exception as e:
        for d in domains_batch:
            results.append({
                "Domain": d['domainName'],
                "Scope": d['validationScope'],
                "Status Code": "Exception",
                "Result": "Exception",
                "Error Detail": str(e)
            })

    return results

def process_domains(input_file, fetch_all, output_file, edgerc_path, section, account_switch_key=None, delay=0, limit=0, batch_size=50):
    """
    Main processing function.
    """
    session, base_url = setup_authentication(edgerc_path, section)
    
    domain_entries = []
    
    if fetch_all:
        # fetch_all_domains still returns list of dicts: {'domain': '...', 'scope': '...'}
        # We need to normalize keys to match read_domains: 'domainName', 'validationScope'
        raw_entries = fetch_all_domains(session, base_url, account_switch_key)
        for entry in raw_entries:
            domain_entries.append({
                "domainName": entry.get('domain'),
                "validationScope": entry.get('scope')
            })
        print(f"[INFO] Fetched {len(domain_entries)} domains from API.")
    elif input_file:
        print(f"[INFO] Reading domains from {input_file}...")
        domain_entries = read_domains(input_file)
    else:
        print("[ERROR] No input provided. Use --all or provide an input file.")
        sys.exit(1)
    
    all_results = []
    
    print("[INFO] Starting Validation Submission (Bulk)...")
    if account_switch_key:
        print(f"[INFO] Using Account Switch Key: {account_switch_key}")
    if limit > 0:
        print(f"[INFO] Limit set to: {limit} (Note: Batching might slightly exceed limit if not aligned)")

    # Apply Limit if set
    if limit > 0:
        domain_entries = domain_entries[:limit]
        print(f"[INFO] Processing limited to first {len(domain_entries)} domains.")

    # Process in Batches
    total = len(domain_entries)
    
    try:
        for i in range(0, total, batch_size):
            batch = domain_entries[i:i+batch_size]
            print(f"[INFO] Processing batch {i//batch_size + 1} ({len(batch)} domains)...")
            
            # Submit Batch
            batch_results = bulk_submit_validation(session, base_url, batch, account_switch_key)
            all_results.extend(batch_results)
            
            # Delay
            if delay > 0 and (i + batch_size < total):
                time.sleep(delay)
                
    except KeyboardInterrupt:
        print("\n[WARN] Script interrupted by user! Saving progress...")
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}. Saving progress...")
    finally:
        # Safety Save
        print(f"[INFO] Writing results to {output_file}...")
        try:
            if all_results:
                results_df = pd.DataFrame(all_results)
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
    parser.add_argument("--batch-size", type=int, default=50, help="Number of domains to submit in one request (Default: 50)")
    
    args = parser.parse_args()
    
    if not args.input_file and not args.all:
        parser.error("You must provide either an input_file or --all")
    
    process_domains(args.input_file, args.all, args.output, args.edgerc, args.section, args.ask, args.delay, args.limit, args.batch_size)
