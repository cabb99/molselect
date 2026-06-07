This directory contains some files that contain alternative locations, multiple models, nucleic chains and modified aminoacids and heteroatoms.

1zbl.cif was modified to include only one model as currently vmd can't parse multiple models from th ecif format, instead parsing them as a single one with multiple alternative locations
It was also modified to remove the OXT atom that is considered a protein on prody an molscene and not a portein for VMD