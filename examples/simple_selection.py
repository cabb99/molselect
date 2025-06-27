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

# Use the new parse method for simple selection
result = selector.parse(df, 'hetatm')

# Print the resulting DataFrame
print(result.df)

#Write the parser grammar to text for debugging purposes
with open("parser_grammar.txt", "w") as f:
    f.write(selector.parser.grammar)
