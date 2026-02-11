# Akamai Domain Ownership Manager Automation Walkthrough

This walkthrough documents the creation and usage of the Python script for automating Akamai Domain Ownership Manager entries.

## 1. Solution Overview
The solution is a Python script (`akamai_dom_script.py`) that:
1.  Reads domain names from an Excel file.
2.  Authenticates with Akamai APIs using `edgegrid-python`.
3.  Sends a `POST` request to the Domain Validation API for each domain.
4.  Parses the response (accepting `201` and `207` status codes) to extract the **TXT Record Name** and **Token Value**.
5.  **Handles existing domains**: If a domain already exists, the script automatically fetches the current validation token via a `GET` request.
6.  Exports the results to a new Excel file.
7.  **Data Normalization**: Automatically converts all input domains to lowercase to prevent API errors.
8.  **Status Handling**: If a domain is already `VALIDATED`, the script marks it as such instead of failing to find a token.

## 2. Usage

### Prerequisites
- Python 3 installed.
- Akamai API credentials with **Domain Validation** (Read-Write) access in `~/.edgerc`.
- Dependencies installed: `pip install -r requirements.txt`.

### Running the Script
Run the script from the command line, providing the path to your input Excel file:

```bash
python3 akamai_dom_script.py /path/to/domains.xlsx
```

Optional arguments:
- `-o`: Specify output file path (default: `results.xlsx`).
- `-e`: Specify `.edgerc` path (default: `~/.edgerc`).
- `-s`: Specify `.edgerc` section (default: `default`).
- `--ask`: Optional **Account Switch Key** to append `accountSwitchKey=<value>` to all API calls.

### Input Format
The input Excel file must have a header row with a column named `Domain` or `Hostname`.

### Output Format
The results Excel file will contain:
- `Domain`: The input domain.
- `Name`: The TXT record name (e.g., `_akamai-domain-challenge.example.com`).
- `Token`: The TXT record value.

## 3. Verification
We verified the solution by:
- Creating a debug script to inspect the API's behavior and confirmed the correct payload structure is `{"domains": [{"domainName": "...", "validationScope": "DOMAIN"}]}`.
- Confirming the API returns a `207 Multi-Status` response for success.
- Extracting the token from `validationChallenge.txtRecord.value`.
- Confirmed the script correctly handles existing domains by catching the "Domain already exists" error and falling back to a `GET` request.
- Verifying the final script correctly processes a list of domains and generates the expected 3-column Excel output.

## 4. Rate Limiting
Akamai APIs typically enforce rate limits (e.g., ~100 requests/minute). 
- **Current Behavior:** The script processes domains sequentially. Unless your network latency is extremely low, you are unlikely to hit this limit with normal usage.
- **Large Batches:** For lists > 500 domains, use the `--delay` argument to slow down processing and avoid `429 Too Many Requests` errors.
- **Recommendation:** `python3 akamai_dom_script.py domains.xlsx --delay 1.5` will ensure you stay well under the limit.

## 5. Safety Mechanism
The script includes a safety mechanism to prevent data loss.
- **Interrupts:** If you stop the script (e.g., `Ctrl+C`) or if it crashes, it will **automatically save** all domains processed up to that point to the output file.
- **Resume:** You can inspect the partial output file to see which domains were completed.

## 6. Domain Validation Trigger Script
We also created a secondary script, `akamai_dom_validate.py`, for domains that are already created but pending validation.
- **Workflow**:
    1.  **Check Status**: `GET /domain-validation/v1/domains/{domain}`
    2.  **Logic**:
        -   If `REQUEST_ACCEPTED` or `VALIDATION_IN_PROGRESS`: Triggers `POST /domain-validation/v1/domains/validate-now`.
        -   Otherwise: Skips the domain.
- **Output**: Generates `validation_results.xlsx` detailing the previous and final status for each domain.
