"""emailextract.evals: the evaluation layer (D11).

The label loader lives here and **never imports the parser**: labels are the
independent side of the comparison (``emailextract.evals.labels``). The L1
oracle arrives in Turn 0.4 (``emailextract.evals.l1``).
"""
