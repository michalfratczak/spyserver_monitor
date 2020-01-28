#!/usr/bin/env python3

'''
	JUST LIST CONTENT OF *.db
'''

import sys
import sqlite3
# import pandas as pd

db = sqlite3.connect(sys.argv[1])
c = db.cursor()
c.execute('SELECT * FROM connections')
for r in c.fetchall():
	print(r)
