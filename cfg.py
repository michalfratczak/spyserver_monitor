#!/usr/bin/env python3

import string
import os
import sys
import configparser
from copy import deepcopy
from pprint import pprint
from get_ip import get_ip_local, get_ip_world

_CFG = None
_CFG_FILE = None

def cfg(i_cfg_file = None):
	global _CFG
	global _CFG_FILE

	if i_cfg_file == None and _CFG:
		return deepcopy(_CFG)

	if not i_cfg_file or not os.path.isfile(i_cfg_file):
		raise ValueError( "Config file does not exist: " + str(i_cfg_file) )

	if _CFG_FILE and _CFG_FILE != i_cfg_file:
		_CFG = None

	if not _CFG:
		_CFG_FILE = i_cfg_file
		print("Loading config from ", _CFG_FILE, ' ... ' , end = '')

		config = configparser.SafeConfigParser()
		config.read(_CFG_FILE)

		# convert config to dictionary
		#
		res = {
			'default': {}
		}

		defaults = config.defaults()
		for k in defaults:
			res['default'][k] = defaults[k]

		for section in config.sections():
			if section not in res:
				res[section] = {}
			for option in config.options(section):
				res[section][option] = config.get(section,option)

		# some config parsing
		#

		# format DB/ip_filters
		ip_filters = res['DB']['ip_filters'].split(',')
		ip_filters = list( map( str.strip, ip_filters ) )

		ipl = None
		while not ipl:
			print("Checking local IP")
			ipl = get_ip_local()

		ipw = None
		while not ipw:
			print("Checking world IP")
			ipw = get_ip_world()

		ip_filters = list( map( lambda x: x.replace('ip_local',ipl), ip_filters) )
		ip_filters = list( map( lambda x: x.replace('ip_world',ipw), ip_filters) )
		# check for any new line characters - this indicates missing commas
		if list(filter( lambda x: '\n' in x, ip_filters )):
			raise RuntimeError("INI File Error: DB/ip_filters should be comma separated list")
		res['DB']['ip_filters'] = ip_filters

		# format SPYSERVER/cfg_list - it should be comma separated
		cfg_list = res['SPYSERVER']['cfg_list'].split(',')
		cfg_list = list( map( str.strip, cfg_list ) )
		cfg_list = list( map( lambda x: x.replace('~', os.environ['HOME']), cfg_list) )
		# check for any new line characters - this indicates missing commas
		if list(filter( lambda x: '\n' in x, cfg_list )):
			raise RuntimeError("INI File Error: SPYSERVER/cfg_list should be comma separated list")
		res['SPYSERVER']['cfg_list'] = cfg_list

		res['SPYSERVER']['exe'] = res['SPYSERVER']['exe'].replace('~', os.environ['HOME'])
		res['DB']['file'] = res['DB']['file'].replace('~', os.environ['HOME'])

		res['MONITOR']['ignore_local_connections'] = \
				res['MONITOR']['ignore_local_connections'].lower() == 'yes' \
			or	res['MONITOR']['ignore_local_connections'].lower() == '1'

		# slack
		res['SLACK']['use'] = \
				res['SLACK']['use'].lower() == 'yes' \
			or	res['SLACK']['use'].lower() == '1'

		if res['SLACK']['use'] and not res['SLACK']['key']:
			raise RuntimeError("No SLACK key provided. Update INI file.")

		# geoloc
		if not res['GEOIP']['key']:
			raise RuntimeError("No IP Geolocation key provided. Update INI file.")

		if res['DB']['ip'].lower() == 'ip_local':
			res['DB']['ip'] = ipl

		for f in res['SPYSERVER']['cfg_list']:
			if not os.path.isfile(f):
				raise RuntimeError("Spyserver config file does not exist: " + f)


		_CFG = res
		print('OK')

	return deepcopy(_CFG)


if __name__ == "__main__":
	pprint( cfg(sys.argv[1]) )
	print( type( cfg(sys.argv[1])['SPYSERVER']['cfg_list'] ) )