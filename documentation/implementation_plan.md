# Akamai Domain Ownership Manager Script Implementation Plan

## Goal Description
Create a Python script that automates the creation of Domain Ownership Manager entries via Akamai API.
The script will read a list of domains from an Excel file, register them with the DOMAIN scope using the Akamai Domain Validation API, retrieve the DNS TXT token, and export the results to a new Excel file.

## User Review Required
> [!IMPORTANT]
> The script requires valid Akamai API credentials. Please follow the setup instructions below.

## Proposed Changes
### Script Logic
#### [NEW] [akamai_dom_script.py](file:///Users/jacoe/.gemini/antigravity/scratch/akamai_dom_script/akamai_dom_script.py)
1.  **Dependencies Explanation**:
    -   `pandas`: Used for reading and writing Excel files efficiently. It handles the data structure (DataFrame) for the list of domains.
    -   `openpyxl`: A dependency of `pandas` required specifically for reading/writing `.xlsx` files.
    -   `requests`: A standard HTTP library for Python, used to make API calls to Akamai.
    -   `edgegrid-python`: The official Akamai library for signing API requests with the EdgeGrid authentication scheme.
2.  **Input**: Reads `domains.xlsx` (user provided path).
    -   **Normalization**: Automatically converts all domain names to lowercase to prevent API errors with mixed-case inputs.
3.  **Authentication**: Uses `EdgeGridAuth` from `~/.edgerc`.
    -   **Setup Instructions for ~/.edgerc**:
        1.  Log in to Akamai Control Center.
        2.  Go to **Identity & Access > API Clients**.
        3.  Create a new API client with **Domain Validation** access (Read-Write).
        4.  Download the credentials or copy the `host`, `client_token`, `client_secret`, and `access_token`.
        5.  Create a file named `.edgerc` in your home directory (`~/.edgerc`).
        6.  Add the following format to the file:
            ```ini
            [default]
            host = your-akamai-host.luna.akamaiapis.net
            client_token = your-client-token
            client_secret = your-client-secret
            access_token = your-access-token
            ```
        7.  The script will look for the section `[default]` by default, or you can specify another section name.
4.  **API Interaction**:
    -   Endpoint: `POST /domain-validation/v1/domains`.
    -   Payload: `{"hostname": <domain>}`.
    -   Response: Extracts the `token` for DNS TXT record.
        -   **Status Handling**: Checks both `status` and `domainStatus` fields. If either is `VALIDATED` (even if no token is returned), the script marks it as "Already Validated".
5.  **Output**: Writes `results.xlsx` containing Domain, Name, and Token.
6.  **Optional Parameters**:
    -   `--ask`: Optional Account Switch Key to include in API calls as `accountSwitchKey=<value>`.
    -   `--delay`: Optional delay in seconds between API calls to avoid rate limits (default: 0).
7.  **Safety Mechanism**:
    -   Implements a `try...finally` block around the processing loop to ensure `results.xlsx` is written even if the script is interrupted (e.g., Ctrl+C) or crashes.

#### [NEW] [akamai_dom_validate.py](file:///Users/jacoe/.gemini/antigravity/scratch/akamai_dom_script/akamai_dom_validate.py)
This script is similar to `akamai_dom_script.py` but focuses on *triggering the validation check* for existing domains based on their current status.
1.  **Input**: Reads domain list from Excel.
2.  **API Interaction Workflow**:
    -   **Step 1: Check Status** (`GET /domain-validation/v1/domains/{domain}`)
        -   If `domainStatus` is `REQUEST_ACCEPTED` or `VALIDATION_IN_PROGRESS`: Proceed to Step 2.
        -   Else: Log the status and skip to next domain.
    -   **Step 2: Submit Validation** (`POST /domain-validation/v1/domains/validate-requests`)
        -   Payload: `{"domains": [{"domainName": domain, "validationScope": "DOMAIN", "validationMethod": "DNS_TXT"}]}`.
        -   Response: Captures the new `domainStatus` from the response.
3.  **Output**: Writes `validation_results.xlsx` with columns: `Domain`, `Status`, `Message`.
4.  **Shared Features**: Authentication, Normalization, Accountability (`--ask`), Rate Limiting (`--delay`), and Safety Save.
5.  **New Feature (--all)**:
    -   Adds `--all` flag to fetch *all* domains from `GET /domain-validation/v1/domains`.
    -   Refactors `check` and `submit` functions to use the specific `validationScope` returned by the API (or default to `DOMAIN` for Excel input).
    -   Makes `input_file` argument optional when `--all` is used.

## Verification Plan
### Automated Tests
-   Verify script syntax and module imports.
-   Mock API response to test Excel read/write logic without hitting actual Akamai API.

### Manual Verification
-   User to provide a test Excel file with 1-2 domains.
-   Run the script and verify `results.xlsx` is created.
-   Check Akamai Control Center to verify the domains have been added.
