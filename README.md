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

This script is used to **submit** a validation check for domains that have already been created and have the TXT record in place.

### Usage

```bash
python3 akamai_dom_validate.py domains.xlsx
```

### Options
-   `--output` or `-o`: Specify the output file name (default: `validation_results.xlsx`).
-   `--edgerc` or `-e`: Specify a custom path to the `.edgerc` file (default: `~/.edgerc`).
-   `--section` or `-s`: Specify the section in `.edgerc` to use (default: `default`).
-   `--ask`: Optional Account Switch Key.
-   `--delay`: Optional delay in seconds between API calls to avoid rate limits.

### Output
The script generates an Excel file (default: `validation_results.xlsx`) with the following columns:
- **Domain**: The domain name processed.
- **Previous Status**: The status retrieved via GET (e.g., `REQUEST_ACCEPTED`, `VALIDATED`).
- **Final Status**: The result of the operation.
  - `Submitted`: "Validate Now" request successfully triggered.
  - `Skipped`: Domain was not in a state to be validated.
  - `Failed`: API error.
- **Message**: Detailed message explaining the action taken.
