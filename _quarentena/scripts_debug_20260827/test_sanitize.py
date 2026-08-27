#!/usr/bin/env python3
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.ipc_handlers import _sanitize_observation

# Test cases
test_cases = [
    "Normal error",
    "Error with sk-1234567890abcdef",
    "Error with api_key=secret",
    "Error with token=secret",
    "Error with Bearer sk-1234567890abcdef",
    "Error with multiple sk-123 and token=456",
    "Error with no sensitive data",
    "",
    None,
]

for case in test_cases:
    if case is None:
        case_str = "None"
        result = _sanitize_observation(case)
    else:
        case_str = repr(case)
        result = _sanitize_observation(case)
    print(f"Input: {case_str}")
    print(f"Output: {result}")
    print()