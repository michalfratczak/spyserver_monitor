#!/usr/bin/env python3


import os
import string
import subprocess
from pprint import pprint

def get_proc():
	res = []
	p = subprocess.Popen(["ps", "-A"], stdout=subprocess.PIPE, universal_newlines=True)
	line = p.stdout.readline()
	while line:
		if '<defunct>' not in line:
			res.append(line)
		line = p.stdout.readline()
	return res

def get_dsp_id(p_arr, p_name = "spyserver"):
	res = []
	for p in p_arr:
		if p_name in p:
			tokens = p.split()
			pid = int(tokens[0])
			res.append(pid)
	return res

def KillProcess(i_proc_name):
	pids = get_dsp_id(get_proc(), i_proc_name)
	while pids:
		for pid in pids:
			print('kill -9 %d' % pid)
			os.system('kill -9 %d' % pid)
		pids = get_dsp_id(get_proc(), i_proc_name)

if __name__ == '__main__':
	KillProcess("SpyServerMon.py")
	KillProcess("spyserver")
