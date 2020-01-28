#!/usr/bin/env python3

import string
import os
import sys
import re
import datetime
import pexpect
import threading
import traceback
import inspect
import json
import time
from pprint import pprint, pformat
from IPy import IP

import urllib
import urllib3
urllib3.disable_warnings()
http = urllib3.PoolManager()

from cfg import cfg

from ConnectionsDB import Connection
from get_ip import get_ip_local, get_ip_world
from NotifySlack import NotifySlack


C_RED = "\033[1;31m"
C_GREEN = "\033[1;32m"
C_BROWN = "\033[1;33m"
C_BLUE = "\033[1;34m"
C_MAGENTA = "\033[1;35m"
C_CYAN = "\033[1;36m"
C_LIGHTGREY = "\033[1;37m"
C_OFF = "\033[0m"
C_CLEAR = "\033[2K"

G_COLORS = [C_RED, C_MAGENTA, C_GREEN, C_CYAN, C_BLUE]
def next_color():
	next_color.i = next_color.i+1
	return G_COLORS[ next_color.i%len(G_COLORS) ]
next_color.i = -1


class SpyServerMonitor():
	'''
	parse STDOUT from spyserver
	and handle actions:
		Accepted client ...
		Client disconnected ...
	'''
	def __init__(self, spyserver_path, config_file, http_addr_pair, no_lan_skip = False):
		if not os.path.isfile(spyserver_path):
			raise ValueError('Bad path to spyserver: ', spyserver_path)
		# if not os.path.isfile(config_file):
		# 	raise ValueError('Bad path to config_file: ', config_file)

		self.__thread = None

		self.__ss = spyserver_path
		self.__config = config_file # spyserver config file
		self.__id = os.path.basename(self.__config)

		self.__db = None

		self.__http_url = http_addr_pair #['port', 'ip']

		self.__no_lan_skip = no_lan_skip

		self.connections = {} # keep active connections (keys) and it's start time (values)

		self.__color = next_color()


	def __str__(self):
		return ( self.__id + " : Connections " + str(len(self.connections.keys())) )

	def __repr__(self):
		return self.__str__()


	def log(self, *args):
		now = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
		print(self.__color, now, self.__id, '==>', args, C_OFF)


	def HandleConnect(self, i_line):
		m = re.match('Accepted client (\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\:(\d+) running SDR# (.+) on (.+)', i_line)
		if not m:
			return False
		grps = m.groups()

		connection = Connection()
		connection['server_instance'] = self.__id
		try:
			connection['ip'] = grps[0]
			connection['port'] = grps[1]
			connection['sdr_version'] = grps[2]
			connection['os'] = grps[3]
		except:
			print(self.__color, traceback.format_exc(), C_OFF)

		if not self.__no_lan_skip and IP(connection['ip']).iptype() == 'PRIVATE':
			self.log("Not logging connection from this LAN: ", connection['ip'])
			return

		if connection in self.connections:
			self.log("Already Connected ??")

		try:
			_url = ':'.join( self.__http_url ) + '/ssmon/api/v1/open'
			postreq = http.request(	'POST', _url,
									headers = {'Content-Type': 'application/json'},
									body = connection.json() )
		except:
			print(self.__color, traceback.format_exc(), C_OFF)
			print(self.__color, self.__id, "HandleConnect -- Error HTTP POST ", _url, C_OFF)
			return False


		# server returned connection updated with geolocation info
		connection.json( postreq.data.decode('utf-8') )
		self.connections[connection] = connection

		return True # handled successfully


	def HandleDisconnect(self, i_line):
		m = re.match('Client disconnected: (\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\:(\d+).*', i_line)
		if not m:
			return False

		connection = Connection()
		connection['server_instance'] = self.__id
		grps = m.groups()
		try:
			connection['ip'] = grps[0]
			connection['port'] = grps[1]
		except:
			print(self.__color, self.__id, C_OFF)
			print(self.__color, traceback.format_exc(), C_OFF)

		if not self.__no_lan_skip and IP(connection['ip']).iptype() == 'PRIVATE':
			print(self.__color, self.__id, "Not logging connection from this LAN: ", connection['ip'], C_OFF)
			return

		if connection in self.connections:
			# connection['start'] = self.connections[connection]['start']
			connection = self.connections[connection]
			del self.connections[connection]
		else:
			self.log("Unknown connection")
			return False

		connection['end'] = datetime.datetime.utcnow()
		dur = connection['end'] - connection['start']
		connection['duration'] = dur.total_seconds()
		self.log(': Duration ', str(dur))

		try:
			_url = ':'.join( self.__http_url ) + '/ssmon/api/v1/close'
			postreq = http.request(	'POST', _url,
									headers = {'Content-Type': 'application/json'},
									body = connection.json())
		except:
			print(self.__color, traceback.format_exc(), C_OFF)
			print(self.__color, self.__id, "HandleDisconnect -- Error HTTP POST ", _url, C_OFF)


		return True # handled successfully


	def HandleRtlGarbage(self, i_line):
		m = re.match('\[R82XX\] PLL not locked!', i_line)
		if m:
			return True
		m = re.match('Found Rafael Micro R820T tuner', i_line)
		if m:
			return True
		return False


	def LineHandler(self, i_line, *args, **kwargs):
		if isinstance(i_line, bytes):
			i_line = i_line.decode("utf-8")
		i_line = i_line.strip()

		if self.HandleRtlGarbage(i_line):
			return

		self.log(i_line)

		if self.HandleConnect(i_line):
			return
		if self.HandleDisconnect(i_line):
			return


	def __run__(self):
		self.P = pexpect.spawn(self.__ss + ' ' + self.__config, timeout=None)
		line = self.P.readline()
		while line:
			try:
				self.LineHandler(line)
			except:
				print(traceback.format_exc())
			line = self.P.readline()


	def Start(self):
		self.__thread__  = threading.Thread(target = self.__run__)
		try:
			self.__thread__.start()
		except KeyboardInterrupt:
			print(self.__color, self.__id, "Sending Ctrl+C to spyserver", C_OFF)
			self.P.sendcontrol('C') # ctrl+C
			self.__thread__.join()
		except:
			print(self.__color, traceback.format_exc(), C_OFF)


	def Stop(self):
		self.log("Sending Ctrl+C to spyserver")
		self.P.sendcontrol('C') # ctrl+C
		if self.__thread__.is_alive():
			self.__thread__.join()




def	main():

	# load config
	config_file = './user.ini'
	if len(sys.argv) > 1:
		config_file = sys.argv[1]
	cfg(config_file)
	pprint(cfg())
	print("\n")

	# spyserver instances
	exec_path = cfg()['SPYSERVER']['exe']
	spy_configs = cfg()['SPYSERVER']['cfg_list']

	SPYSERVERS = []
	for spy_conf in spy_configs:
		SPYSERVERS.append(
				SpyServerMonitor( 	exec_path, spy_conf,
									[cfg()['DB']['ip'], cfg()['DB']['port']],
									no_lan_skip = not cfg()['MONITOR']['ignore_local_connections'] )
			)

	for ss in SPYSERVERS:
		ss.Start()
		time.sleep(1)

	try:
		while(True):
			time.sleep(1)
	except KeyboardInterrupt:
		pass
	except:
		print(traceback.format_exc())

	for ss in SPYSERVERS:
		try:
			ss.Stop()
		except:
			print(traceback.format_exc())


if __name__ == "__main__":
	try:
		import setproctitle
		setproctitle.setproctitle('SpyServerMon.py')
	except:
		pass
	main()
