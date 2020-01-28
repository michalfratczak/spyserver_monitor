#!/usr/bin/env python3

import sys
import time

'''
	spyserver mockup
'''

def TestOpen(i_pause = None):
	print('Accepted client 100.200.30.40:5678 running SDR# 1700.0.0.1 on Windows')

def TestClose():
	print('Client disconnected: 100.200.30.40:5678')

if __name__ == "__main__":
	pause = 5 # int(sys.argv[1])

	TestOpen(pause)

	if pause:
		time.sleep(pause)
	TestClose()