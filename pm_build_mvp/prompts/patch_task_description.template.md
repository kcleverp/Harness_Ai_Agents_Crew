The file '{file_path}' failed Schema Validation.
Exact errors found:
{error_details}

Reference Business Logic:
{founder_context}

Action Steps:
1. Use 'Safe File Reader Tool' to inspect '{file_path}'.
2. Identify specific key paths that are broken.
3. Use 'Apply Partial JSON Patch Tool' repeatedly for each broken path.
4. Never rewrite the full file.