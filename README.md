# Akamai Domain Ownership Manager Script

This script automates the creation of Domain Ownership Manager entries via the Akamai API.

## Setup

1.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

2.  **Configure Akamai Credentials**:
    -   Create a file named `.edgerc` in your home directory (`~/.edgerc`).
    -   Add your Akamai API credentials in the following format:
        ```ini
        [default]
        host = your-akamai-host.luna.akamaiapis.net
        client_token = your-client-token
        client_secret = your-client-secret
        access_token = your-access-token
        ```
    -   Ensure your API client has **Read-Write** access to the **Domain Validation API**.

3.  **Prepare Input File**:
    -   Create an Excel file (e.g., `domains.xlsx`).
    -   **Crucial**: The first row MUST contain a header named `Domain` or `Hostname`.
    -   List your domains in the column below that header.
    -   **Note**: The script will automatically normalize domain names to lowercase.

    | Domain          |
    |-----------------|
    | example.com     |
    | mysite.org      |

## Usage

Run the script from the command line:

```bash
python3 akamai_dom_script.py domains.xlsx
```

### Options

-   `--output` or `-o`: Specify the output file name (default: `results.xlsx`).
-   `--edgerc` or `-e`: Specify a custom path to the `.edgerc` file (default: `~/.edgerc`).
-   `--section` or `-s`: Specify the section in `.edgerc` to use (default: `default`).
-   `--ask`: Optional Account Switch Key to include in API calls (e.g., `1-599K`).
-   `--delay`: Optional delay in seconds between API calls to avoid rate limits (e.g., `1.5`).

### Safety Features
-   **Interrupt Handling**: If you stop the script (e.g., `Ctrl+C`) or it crashes, it will automatically save all processed domains to the output file before exiting. This prevents data loss during long runs.
-   **Rate Limiting**: Use the `--delay` parameter to slow down execution for large batches (500+ domains).

**Example**:
```bash
# Using relative paths (files in current folder)
python3 akamai_dom_script.py my_domains.xlsx -o my_results.xlsx

# Using absolute paths
python3 akamai_dom_script.py /Users/me/Documents/domains.xlsx -o /Users/me/Desktop/results.xlsx
```

## Output
The script generates an Excel file (default: `results.xlsx`) with the following columns:
- **Domain**: The domain name processed.
- **Name**: The name of the TXT record to be created (e.g., `_akamai-domain-challenge.example.com`).
- **Token**: The value for the TXT record.
  - If the domain is already validated, this will show: `Already Validated`.
  - If an error occurs, it will show the error message.

## Domain Validation Trigger Script (`akamai_dom_validate.py`)

This script is used to **submit** a validation check for domains that have already been created and have a pending status (`REQUEST_ACCEPTED` or `VALIDATION_IN_PROGRESS`).

### Usage

**Option 1: Validate specific domains from a file**
```bash
python3 akamai_dom_validate.py domains.xlsx
```

**Option 2: Validate ALL pending domains in your account**
```bash
# Process all eligible domains
python3 akamai_dom_validate.py --all

# Process a limited batch of eligible domains (e.g., first 50)
python3 akamai_dom_validate.py --all --limit 50
```

### Key Features
-   **Smart Filtering**: When using `--all`, the script fetches all domains but **automatically filters** the list to only include those with status `REQUEST_ACCEPTED` or `VALIDATION_IN_PROGRESS`. All other domains are silently ignored to speed up processing.
-   **Performance Optimized**: Utilizes the initial list-fetch to determine status, avoiding redundant API calls for every domain.
-   **Pagination Support**: Handles large accounts with thousands of domains automatically.

### Options
-   `--all`: Fetch all domains from the Akamai account instead of using an input file.
-   `--limit`: Stop submitting validation requests after a specified number of domains (e.g., `--limit 25`). Useful for testing or batched rollouts.
-   `--output` or `-o`: Specify the output file name (default: `validation_results.xlsx`).
-   `--edgerc` or `-e`: Specify a custom path to the `.edgerc` file (default: `~/.edgerc`).
-   `--section` or `-s`: Specify the section in `.edgerc` to use (default: `default`).
-   `--ask`: Optional Account Switch Key.
-   `--delay`: Optional delay in seconds between API calls to avoid rate limits.

### Output
The script generates an Excel file (default: `validation_results.xlsx`) containing **only the domains that were processed** (i.e., eligible for validation).
Columns:
- **Domain**: The domain name processed.
- **Scope**: The validation scope (e.g., `DOMAIN`, `DV_SAN`).
- **Previous Status**: The status retrieved from the list (e.g., `REQUEST_ACCEPTED`).
- **Final Status**: The result of the operation.
  - `Submitted`: "Validate Now" request successfully triggered.
  - `Skipped (Limit Reached)`: Eligible domain was skipped because the `--limit` count was reached.
  - `Failed`: API error.
- **Message**: Detailed message explaining the action taken.

## Bulk Domain Deletion Script (`akamai_dom_delete.py`)

This script performs a **bulk delete** of domains from the Domain Validation API. It is designed to be robust, handling batch errors intelligently.

### Input File Format
The script expects an Excel file with at least two columns:
- **Domain**: The domain name to delete.
- **validationScope**: The scope of the domain (e.g., `DOMAIN`, `DV_SAN`). **Required**.

| Domain          | validationScope |
|-----------------|-----------------|
| example.com     | DOMAIN          |
| sub.mysite.org  | DV_SAN          |

### Usage

```bash
python3 akamai_dom_delete.py domains.xlsx
```

### Key Features
- **Intelligent Error Handling**: APIs often reject an entire batch if even one domain is invalid (e.g., "Domain not found"). This script automatically:
  1. Detects `400 Bad Request` batch failures.
  2. Identifies exactly which domains were rejected by the API.
  3. Records the specific error for the invalid domains.
  4. **Automatically resubmits** the remaining valid domains from the batch.
- **Batch Processing**: Deletes domains in batches (default 100) to respect API quotas.

### Options
-   `--output` or `-o`: Specify the output file name (default: `delete_results.xlsx`).
-   `--edgerc` or `-e`: Specify a custom path to the `.edgerc` file (default: `~/.edgerc`).
-   `--section` or `-s`: Specify the section in `.edgerc` to use (default: `default`).
-   `--ask`: Optional Account Switch Key.
-   `--batch-size`: Number of domains per batch delete request (default: `100`).

### Output
The script generates an Excel file (default: `delete_results.xlsx`) containing:
- **Domain**: Domain name.
- **Scope**: Validation scope.
- **Result**: `Success` or `Failed`.
- **Error Title/Detail**: Specific API error details (e.g., "Domain is not found") captured directly from the 400 response.
