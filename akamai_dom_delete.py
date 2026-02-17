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

def read_delete_targets(file_path):
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
            print(f"[ERROR] 'validationScope' column required but not found in {file_path}")
            print("Available columns:", list(df.columns))
            sys.exit(1)

        targets = []
        for index, row in df.iterrows():
            d = row[domain_col_name]
            s = row[scope_col_name]
            
            # Simple validation
            if pd.isna(d) or str(d).strip() == '':
                continue
                
            d_str = str(d).strip().lower()
            # Force uppercase for scope as API enums are usually uppercase (e.g. DOMAIN)
            s_str = str(s).strip().upper() if not pd.isna(s) else "DOMAIN" 
            
            targets.append({
                "domainName": d_str,
                "validationScope": s_str
            })
            
        print(f"[INFO] Loaded {len(targets)} domains for deletion from {file_path}")
        return targets

    except Exception as e:
        print(f"[ERROR] Error reading Excel file: {e}")
        sys.exit(1)

def delete_domains(session, base_url, domains_batch, account_switch_key=None):
    """
    Sends a DELETE request for a batch of domains.
    API: DELETE /domain-validation/v1/domains
    
    Handles 400 Bad Request errors by:
    1. Parsing the 'errors' list to identify specific invalid domains.
    2. Failing those specific domains with detailed error messages.
    3. Constructing a new batch with only the valid domains and recursively retrying.
    """
    endpoint = "/domain-validation/v1/domains"
    url = urljoin(base_url, endpoint) 
    
    params = {}
    if account_switch_key:
        params['accountSwitchKey'] = account_switch_key

    payload = {
        "domains": domains_batch
    }
    
    results = []
    
    try:
        # requests.delete allows 'json' parameter
        response = session.delete(url, json=payload, params=params)
        status_code = response.status_code
        
        # 400 Bad Request: Usually means one or more domains in the batch are invalid (e.g. not found).
        # We need to parse the response to find out which ones, fail them, and retry the rest.
        if status_code == 400:
            print(f"[WARN] Batch failed with 400. Attempting to parse errors and retry valid domains...")
            
            try:
                error_data = response.json()
                errors_list = error_data.get('errors', [])
                
                # Identify indices of domains that caused the error
                # Field format example: "domains[2].domainName" -> Index 2
                bad_indices = set()
                for err in errors_list:
                    field = err.get('field', '')
                    if field.startswith('domains[') and ']' in field:
                         try:
                             idx_str = field.split('[')[1].split(']')[0]
                             bad_indices.add(int(idx_str))
                         except:
                             pass
                
                if not bad_indices:
                     # Could not identify specific domains, fail the whole batch
                     print("[ERROR] Could not identify specific bad domains in 400 response. Failing batch.")
                     for d in domains_batch:
                        results.append({
                            "Domain": d['domainName'],
                            "Scope": d['validationScope'],
                            "Status Code": status_code,
                            "Result": "Failed",
                            "Error Title": error_data.get('title'),
                            "Error Detail": error_data.get('detail')
                        })
                else:
                    # Separation: Bad vs Potentially Good
                    retry_batch = []
                    
                    for i, d in enumerate(domains_batch):
                        if i in bad_indices:
                            # Record the specific failure for this domain
                            specific_detail = error_data.get('detail')
                            # Try to find the exact error message for this specific index
                            for err in errors_list:
                                if f"domains[{i}]" in err.get('field', ''):
                                    specific_detail = err.get('detail')
                                    break
                            
                            results.append({
                                "Domain": d['domainName'],
                                "Scope": d['validationScope'],
                                "Status Code": status_code,
                                "Result": "Failed",
                                "Error Title": "Invalid Request",
                                "Error Detail": specific_detail
                            })
                        else:
                            # This domain was not cited in the errors, so it might be valid.
                            retry_batch.append(d)
                    
                    if retry_batch:
                        print(f"[INFO] Retrying {len(retry_batch)} valid domains from the failed batch...")
                        # Recursive call to process the remaining valid domains
                        retry_results = delete_domains(session, base_url, retry_batch, account_switch_key)
                        results.extend(retry_results)

            except Exception as e:
                 print(f"[ERROR] Exception during 400 parsing/retry: {e}")
                 # Fallback: Fail everything if logic breaks to avoid infinite loops or data loss
                 for d in domains_batch:
                    # Avoid duplicating if already added
                    if not any(r.get('Domain') == d['domainName'] for r in results):
                        results.append({
                            "Domain": d['domainName'],
                            "Scope": d['validationScope'],
                            "Status Code": status_code,
                            "Result": "Failed",
                            "Error Detail": f"Batch failed and retry logic crashed: {str(e)}"
                        })

        elif status_code in (200, 204):
            # Success (204 No Content is standard for DELETE)
            for d in domains_batch:
                results.append({
                    "Domain": d['domainName'],
                    "Scope": d['validationScope'],
                    "Status Code": status_code,
                    "Result": "Success",
                    "Details": "Deleted successfully"
                })
        
        elif status_code == 207:
             # Multi-status: The API might return individual status for each item (rare for this specific V1 endpoint but good practice)
             try:
                 data = response.json()
                 for d in domains_batch:
                     results.append({
                        "Domain": d['domainName'],
                        "Scope": d['validationScope'],
                        "Status Code": status_code,
                        "Result": "Multi-Status",
                        "Details": str(data)
                     })
             except:
                  for d in domains_batch:
                     results.append({
                        "Domain": d['domainName'],
                        "Scope": d['validationScope'],
                        "Status Code": status_code,
                        "Result": "Multi-Status",
                        "Details": response.text
                     })
        else:
            # Other errors (401, 403, 500, etc.)
            for d in domains_batch:
                results.append({
                    "Domain": d['domainName'],
                    "Scope": d['validationScope'],
                    "Status Code": status_code,
                    "Result": "Error",
                    "Details": response.text
                })
                
    except Exception as e:
        # Network or other unhandled exceptions
        for d in domains_batch:
            results.append({
                "Domain": d['domainName'],
                "Scope": d['validationScope'],
                "Status Code": "Exception",
                "Result": "Exception",
                "Error Detail": str(e)
            })

    return results

def main():
    parser = argparse.ArgumentParser(description="Bulk Delete Domains via Akamai API")
    parser.add_argument("input_file", help="Path to the domains.xlsx file")
    parser.add_argument("--output", "-o", default="delete_results.xlsx", help="Output file for results")
    parser.add_argument("--edgerc", "-e", default=os.path.expanduser("~/.edgerc"), help="Path to .edgerc file")
    parser.add_argument("--section", "-s", default="default", help="Section in .edgerc to use")
    parser.add_argument("--ask", help="Optional Account Switch Key")
    # Batch size?
    parser.add_argument("--batch-size", type=int, default=100, help="Number of domains to delete in one request")

    args = parser.parse_args()
    
    # Setup Auth
    session, base_url = setup_authentication(args.edgerc, args.section)
    
    # Read Targets
    targets = read_delete_targets(args.input_file)
    if not targets:
        print("[INFO] No targets found to delete.")
        sys.exit(0)
    
    all_results = []
    
    # Process in batches
    total = len(targets)
    batch_size = args.batch_size
    
    print(f"[INFO] Starting bulk delete for {total} domains...")
    
    for i in range(0, total, batch_size):
        batch = targets[i:i+batch_size]
        print(f"[INFO] Processing batch {i//batch_size + 1} ({len(batch)} domains)...")
        
        batch_results = delete_domains(session, base_url, batch, args.ask)
        all_results.extend(batch_results)
        
        # Small delay to be nice to API?
        time.sleep(1)
        
    # Save Results
    print(f"[INFO] Saving results to {args.output}...")
    try:
        df_out = pd.DataFrame(all_results)
        df_out.to_excel(args.output, index=False)
        print("[INFO] Done.")
    except Exception as e:
        print(f"[ERROR] Failed to save results: {e}")

if __name__ == "__main__":
    main()
