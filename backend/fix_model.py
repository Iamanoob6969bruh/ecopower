import re

input_path = r"c:\Users\wadaf\OneDrive\Desktop\RF\solar_lightgbm.txt"
output_path = r"c:\Users\wadaf\OneDrive\Desktop\RF\solar_lightgbm_fixed.txt"

with open(input_path, 'r') as f:
    lines = f.readlines()

fixed_lines = []
in_trees = True
in_params = False

for line in lines:
    if line.strip() == "end of trees":
        fixed_lines.append(line)
        in_trees = False
        continue
    
    if line.strip() == "parameters:":
        fixed_lines.append("parameters\n")
        in_params = True
        continue
    
    if line.strip() == "end of parameters":
        fixed_lines.append(line)
        in_params = False
        continue

    if line.strip().startswith("pandas_categorical:"):
        fixed_lines.append(line)
        continue

    if in_trees or in_params:
        fixed_lines.append(line)
    elif line.startswith("Tree="): # Backup if end of trees was missed
        in_trees = True
        fixed_lines.append(line)
    elif line.startswith("version=") or line.startswith("num_class=") or line.startswith("num_tree_per_iteration=") or line.startswith("label_index=") or line.startswith("max_feature_idx=") or line.startswith("objective=") or line.startswith("feature_names=") or line.startswith("feature_infos=") or line.startswith("tree_sizes=") or line.startswith("tree"):
        fixed_lines.append(line)

with open(output_path, 'w') as f:
    f.writelines(fixed_lines)

print(f"Fixed model saved to {output_path}")
