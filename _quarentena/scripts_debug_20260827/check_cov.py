import json

with open(r"C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002\coverage.json") as f:
    d = json.load(f)

totals = d["totals"]
print(f"Total coverage: {totals['percent_covered']:.1f}%")
print(f"Lines: {totals['covered_lines']}/{totals['num_statements']}")
print(f"Missing: {totals['missing_lines']}")