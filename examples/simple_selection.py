"""
A simple example of using molscene and molselect to select protein atoms from a PDB file.
"""

import molscene
import molselect
from molselect.python.evaluator import Evaluator
from molselect.python.backends.pandas import PandasStructure

# Load the PDB file as a Scene
df = molscene.Scene.from_pdb('molselect/data/tests/pdb3mht.pdb')

# Create the evaluator with the backend class
selector = Evaluator(PandasStructure)
#selector.parser = molselect.python.parser.SelectionParser(parser_kwargs={'parser': 'earley', 'ambiguity': 'explicit'}, remove_hidden_tokens=True)

selection_string = "backbone"

#Write the parser grammar to text for debugging purposes
with open("parser_grammar.lark", "w") as f:
    f.write(selector.parser.grammar)

parser = selector.parser
forest = parser.parse(selection_string)

# 'forest' is actually a Tree('_ambig', [tree1, tree2, …])
print(forest.pretty())

# to see them separately:
for idx, subtree in enumerate(forest.children, 1):
    print(f"\n=== Parse #{idx} ===")
    print(subtree.pretty())

# # Use the new parse method for simple selection
result = selector.parse(df, "altloc ''")

# # Print the resulting DataFrame
print(result.df)


