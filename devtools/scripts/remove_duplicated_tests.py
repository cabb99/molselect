"""
Script to comment out all but the first occurrence of each repeated query in selection_tests.jsonc.
Writes the result to selection_tests_corrected.jsonc in the same directory.
"""
import json
from collections import Counter, defaultdict
from pathlib import Path


def main():
    # Correct path: go up two directories to tests/selection_tests.jsonc
    jsonc_path = (Path(__file__).parent.parent.parent / "molselect" /"python" / "tests" / "selection_tests.jsonc").resolve()
    with open(jsonc_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # 1. Strip comments and parse JSON
    clean_lines = [line for line in lines if not line.lstrip().startswith("//")]
    clean_json = "".join(clean_lines)
    try:
        selection_tests = json.loads(clean_json)
    except Exception as e:
        print("Failed to parse JSON after stripping comments:", e)
        selection_tests = []

    # 2. Find repeated queries
    queries = [test["query"] for test in selection_tests]
    query_counts = Counter(queries)
    repeated_queries = {query: count for query, count in query_counts.items() if count > 1}
    if repeated_queries:
        print("Repeated queries found:")
        for query, count in repeated_queries.items():
            print(f"{query}: {count} times")

    # 3. Build a mapping from line number to query value (for lines with a query)
    line_to_query = {}
    test_idx = 0
    for i, line in enumerate(lines):
        if not line.lstrip().startswith("//") and '"query"' in line:
            if test_idx < len(selection_tests):
                line_to_query[i] = selection_tests[test_idx]["query"]
                test_idx += 1

    # 4. Write out the file, commenting only the second and further appearances
    occurrence_counter = Counter()
    corrected_path = jsonc_path.parent / "selection_tests_corrected.jsonc"
    with open(corrected_path, "w", encoding="utf-8") as f:
        for i, line in enumerate(lines):
            query_val = line_to_query.get(i)
            if query_val and query_val in repeated_queries:
                occurrence_counter[query_val] += 1
                if occurrence_counter[query_val] > 1:
                    line = "// " + line
            f.write(line)
    print(f"Corrected file written to {corrected_path}")

if __name__ == "__main__":
    main()
