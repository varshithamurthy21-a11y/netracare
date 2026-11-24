---
name: partner-lab-referrals
description: How to look up and book diagnostic tests (OCT scan, visual field, fundus photo, corneal topography) with partner lab ClearView Diagnostics through its MCP server. Use when a patient asks about lab tests, scans or test prices.
---

# Partner lab (ClearView Diagnostics)

The partner lab is a separate service reached through MCP tools: list_lab_tests, get_test_details, check_lab_slots, book_lab_test, get_order_status, cancel_lab_order.

## Workflow
1. Use list_lab_tests to answer questions about available tests and indicative prices.
2. Only book a test when the patient (or their doctor) asks for it. Collect test, date and time.
3. Present a confirmation (test, date, time, price) and wait for approval before calling book_lab_test.
4. Report the order number and remind the patient that results are shared with their NetraCare doctor.

## Never
Never interpret results or say what a test will show. Never book without approval.
