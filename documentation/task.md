# Akamai Domain Ownership Manager Script

- [x] Initialize project structure and dependencies <!-- id: 0 -->
- [x] Research Akamai Domain Validation API and create implementation plan <!-- id: 1 -->
- [x] Create the Python script <!-- id: 2 -->
    - [x] Implement Excel input reading <!-- id: 3 -->
    - [x] Implement Akamai EdgeGrid authentication <!-- id: 4 -->
    - [x] Implement API call to create domain validation <!-- id: 5 -->
    - [x] Implement Excel output writing <!-- id: 6 -->
- [x] Verify the script logic (dry run or mock) <!-- id: 7 -->
- [x] Debug API errors and refine payload structure <!-- id: 9 -->
- [x] Refine output to include TXT record name <!-- id: 10 -->
- [x] Provide instructions for usage and setup <!-- id: 8 -->
- [x] Cleanup and code review (final polish) <!-- id: 11 -->
- [x] Handle existing domains (fetch token if domain exists) <!-- id: 12 -->
- [x] Implement accountSwitchKey support via --ask argument <!-- id: 13 -->
- [x] Implement rate limit mitigation via --delay argument <!-- id: 14 -->
- [x] Implement safety save on interrupt (try/finally block) <!-- id: 15 -->
- [x] Normalize domains to lowercase <!-- id: 16 -->
- [x] Handle already validated domains (status: VALIDATED) <!-- id: 17 -->

# Bulk Validation Submit Script
- [x] Create implementation plan for Validation Script <!-- id: 18 -->
- [x] Create `akamai_dom_validate.py` script <!-- id: 19 -->
    - [x] Implement Excel input reading (using existing logic) <!-- id: 20 -->
    - [x] Implement API call to submit validation (`POST /{domain}/validate`) <!-- id: 21 -->
    - [x] Implement Excel output writing (Status/Result) <!-- id: 22 -->
- [x] Verify script with dry run/mock <!-- id: 23 -->
- [x] Add documentation to README <!-- id: 24 -->
- [x] Refactor Validation Script Logic <!-- id: 25 -->
    - [x] Logic: GET domain -> Check if status is REQUEST_ACCEPTED or VALIDATION_IN_PROGRESS
    - [x] If yes: POST to validate endpoint (with DNS_TXT and DOMAIN scope)
    - [x] If no: Log status and skip <!-- id: 26 -->
- [ ] Implement `--all` option to fetch all domains <!-- id: 27 -->
    - [ ] Logic: GET /domains (List Domains)
    - [ ] Refactor process loop to handle dynamic `validationScope` from API or default from Excel
    - [ ] Make input file optional if `--all` is used
