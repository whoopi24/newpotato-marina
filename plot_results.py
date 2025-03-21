import json
import random
from collections import Counter

import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np

# Load JSON file
json_file = "evaluation_results.json"
with open(json_file, "r") as f:
    data_dict = json.load(f)

category = "total"  # Choose which precision-recall values to plot ("total", "matches_only", "exact_match")

# Fixed color palette for extractions (black, dark blue, dark gray, dark green, red)
extraction_colors = ["#000000", "#0b3d91", "#808080", "#1a4d2e", "#e41a1c"]

# Generate distinguishable colors for patterns
pattern_colors = plt.get_cmap("tab20")(np.linspace(0, 1, 20))

jitter_strength = 0.001

# Initialize min/max values
min_precision, max_precision = float("inf"), float("-inf")
min_recall, max_recall = float("inf"), float("-inf")

# find global min/max across all evaluations
for evaluations in data_dict.values():
    for eval_data in evaluations:
        results = eval_data["results"]["shg"].get(category, {})
        if "precision" in results and "recall" in results:
            min_precision = min(min_precision, results["precision"])
            max_precision = max(max_precision, results["precision"])
            min_recall = min(min_recall, results["recall"])
            max_recall = max(max_recall, results["recall"])

# expand range slightly for better visualization
padding = 0.05
precision_range = max_precision - min_precision
recall_range = max_recall - min_recall

min_precision -= precision_range * padding
max_precision += precision_range * padding
min_recall -= recall_range * padding
max_recall += recall_range * padding

# collect unique pattern and extraction values
unique_patterns = sorted(
    set(
        eval_data["nr_of_patterns"]
        for evaluations in data_dict.values()
        for eval_data in evaluations
    )
)
unique_extractions = sorted(
    set(
        eval_data["max_nr_of_extractions"]
        for evaluations in data_dict.values()
        for eval_data in evaluations
    )
)

# create color maps
pattern_cmap = mcolors.ListedColormap(pattern_colors[: len(unique_patterns)])
extraction_cmap = mcolors.ListedColormap(extraction_colors[: len(unique_extractions)])

# explicitly setting boundaries
pattern_norm = mcolors.BoundaryNorm(
    unique_patterns + [max(unique_patterns) + 5], pattern_cmap.N
)
extraction_norm = mcolors.BoundaryNorm(
    unique_extractions + [max(unique_extractions) + 1], extraction_cmap.N
)

# create mapping
pattern_to_color = {
    pattern: pattern_colors[i] for i, pattern in enumerate(unique_patterns)
}
extraction_to_color = {
    extraction: extraction_colors[i] for i, extraction in enumerate(unique_extractions)
}

for input_file, evaluations in data_dict.items():
    if not evaluations:
        print(f"Skipping {input_file}: No data available.")
        continue

    # Sort configurations by patterns ↓, then extractions ↓
    evaluations.sort(key=lambda x: (-x["nr_of_patterns"], -x["max_nr_of_extractions"]))

    # Create figure
    plt.figure(figsize=(8, 6))

    precision_values = []
    recall_values = []
    f1_scores = []
    remarks = []

    # Count occurrences of (precision, recall) pairs for jittering
    value_counts = Counter(
        (res["precision"], res["recall"])
        for eval_data in evaluations
        if "precision" in (res := eval_data["results"]["shg"].get(category, {}))
        and "recall" in res
    )

    best_f1 = 0
    best_f1_point = None

    for eval_data in evaluations:
        results = eval_data["results"]["shg"].get(category, {})
        if "precision" not in results or "recall" not in results:
            continue

        precision, recall = results["precision"], results["recall"]

        # Calculate F1 score
        if precision + recall > 0:
            f1_score = 2 * (precision * recall) / (precision + recall)
            f1_scores.append(f1_score)

            # Track best F1 score
            if f1_score > best_f1:
                best_f1 = f1_score
                best_f1_point = (recall, precision)

        # Apply jitter if necessary
        if value_counts[(precision, recall)] > 1:
            precision += random.uniform(-jitter_strength, jitter_strength)
            recall += random.uniform(-jitter_strength, jitter_strength)
            best_f1_point = (recall, precision)

        # Get pattern and extraction configuration
        num_patterns = eval_data["nr_of_patterns"]
        num_extractions = eval_data["max_nr_of_extractions"]

        precision_values.append(precision)
        recall_values.append(recall)

        # Plot the point with face and edge color
        plt.scatter(
            recall,
            precision,
            s=80,
            c=[pattern_to_color[num_patterns]],
            edgecolors=[extraction_to_color[num_extractions]],
            linewidths=1.5,
            alpha=0.8,
        )

        # Store remark if available
        if "remark" in eval_data:
            remarks.append((precision, recall, eval_data["remark"]))

    if not precision_values:
        print(f"Skipping {input_file}: No valid precision-recall data.")
        continue

    # highlight best f1 point
    if best_f1_point:
        plt.text(
            best_f1_point[0],
            best_f1_point[1],
            f".f1: {round(best_f1, 3)}",
            fontsize=10,
            ha="left",
            color="black",
        )

    print(
        f"{input_file}: The maximum f1 score is {round(best_f1, 3)} for point ({round(best_f1_point[0], 3)}, {round(best_f1_point[1], 3)})!"
    )

    # Add remarks as text labels
    for py, rx, remark in remarks:
        plt.text(rx, py, remark, fontsize=9, color="black", alpha=0.75, ha="right")

    # labels and title
    plt.xlabel("Recall")
    plt.ylabel("Precision")
    plt.title(f"Precision-Recall Plot: {input_file}")

    # colorbar for patterns
    # boundaries = np.arange(min(unique_patterns) - 0.5, max(unique_patterns) + 1.5, 1)
    boundaries = np.arange(min(unique_patterns) - 1, max(unique_patterns) + 6, 5)
    tick_positions = boundaries[:-1] + 2.5
    cb1 = plt.colorbar(
        plt.cm.ScalarMappable(norm=pattern_norm, cmap=pattern_cmap),
        ax=plt.gca(),
        ticks=tick_positions,
    )
    cb1.set_ticklabels(unique_patterns)
    cb1.set_label("number of patterns")

    # colorbar for extractions
    boundaries = np.arange(min(unique_extractions) - 1, max(unique_extractions) + 2, 1)
    tick_positions = boundaries[1:-1] + 0.5
    cb2 = plt.colorbar(
        plt.cm.ScalarMappable(norm=extraction_norm, cmap=extraction_cmap),
        ax=plt.gca(),
        ticks=tick_positions,
    )
    cb2.set_ticklabels(unique_extractions)
    cb2.set_label("max. number of extractions")

    # Save plot
    filename = f"prec_rec_{input_file.split('.')[0]}.png"
    plt.savefig(filename, dpi=300, bbox_inches="tight")
    plt.close()

print("Plots saved successfully!")
