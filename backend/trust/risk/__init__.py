"""The risk assessment: which risk drivers are on for a group, and how each risk is rated from them.

Read in this order:
  drivers.py      is one driver on or off for a group?
  expressions.py  reads one rule from a risk file, such as "RD02 in ad and RD54 in ad"
  rating.py       likelihood, impact, applicable, Elevated and the trend for each risk
  files.py        reads the drivers file (the risks are read by trust.config.risks)

Nothing here reads or writes the database, and nothing here changes a TRUST score.
"""
