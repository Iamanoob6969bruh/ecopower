with open(r"c:\Users\wadaf\OneDrive\Desktop\RF\solar_lightgbm.txt", 'r') as f:
    lines = f.readlines()

print(f"Total lines: {len(lines)}")
tree_indices = [i for i, line in enumerate(lines) if line.startswith("Tree=")]
print(f"Number of trees: {len(tree_indices)}")
if tree_indices:
    print(f"First tree at line: {tree_indices[0]+1}")
    print(f"Last tree at line: {tree_indices[-1]+1}")

# Check for "end of trees"
end_of_trees = [i for i, line in enumerate(lines) if "end of trees" in line]
print(f"End of trees at line: {end_of_trees if end_of_trees else 'NOT FOUND'}")

# Check for "parameters"
parameters = [i for i, line in enumerate(lines) if line.strip() == "parameters"]
print(f"Parameters start at line: {parameters if parameters else 'NOT FOUND'}")
