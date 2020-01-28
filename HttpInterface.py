#!/usr/bin/env python3

__all__ = ['RUN']

import os
import sys
import json
import datetime
import traceback
import subprocess
import getpass
import re
from pprint import pprint
import bottle

from cfg import cfg
from ConnectionsDB import ConnectionsDB, Connection
from NotifySlack import NotifySlack

import urllib3
urllib3.disable_warnings()
http = urllib3.PoolManager()

from get_ip import get_ip_local, get_ip_world


def IpMatch(i_ip, i_regexp):
	i_regexp = i_regexp.replace('*', '\d+')

	ip_tokens = i_ip.split('.')
	if len(ip_tokens) != 4:
		print('ipfilter - Bad IP: ', i_ip)
		return False

	re_tokens = i_regexp.split('.')
	if len(re_tokens) != 4:
		print('ipfilter - Bad regexp: ', i_regexp)
		return False

	for i in range(4):
		if not re.match(re_tokens[i], ip_tokens[i]):
			return False
	return True


def IP2GeoLoc(ip, key):
	_url = 'https://api.ipgeolocation.io/ipgeo?apiKey={}&ip={}'.format(key, ip)
	resp = http.request("GET", _url)
	resp = json.loads(resp.data.decode("utf-8"))
	return resp


class JSONEncoder(json.JSONEncoder):
	def default(self, o):
		if isinstance(o, datetime.datetime):
			return str(o)
		elif isinstance(o, Connection):
			return o.json()
		res = ''
		try:
			res = json.JSONEncoder.default(self, o)
		except:
			print('JSON encode error:', type(o))
			res = ''
		return res


class EnableCors(object):
	name = "enable_cors"
	api = 2

	def apply(self, fn, context):
		def _enable_cors(*args, **kwargs):
			# set CORS headers
			bottle.response.headers["Access-Control-Allow-Origin"] = "*"
			bottle.response.headers[
				"Access-Control-Allow-Methods"
			] = "GET, POST, PUT, OPTIONS"
			bottle.response.headers[
				"Access-Control-Allow-Headers"
			] = "Origin, Accept, Content-Type, X-Requested-With, X-CSRF-Token"

			if bottle.request.method != "OPTIONS":
				# actual request; reply with the actual response
				return fn(*args, **kwargs)

		return _enable_cors


application = bottle.app()
application.install(EnableCors())
DB = None
IP_FILTERS = []  # filters to exclude IPs, ie 192.168.*.*

G_NOTIFY_RECIPENTS = []

######################################################################


# i_reg = bottle.request.query
def GetRequestValueWithDefault(i_req, i_token, i_type, defaultValue):
	"""
		get value from GET request
		ensure proper type
		return defaultValue on error or missing
		"""
	if type(defaultValue) != i_type:
		raise ValueError("defaultValue is of wrong type")

	if i_token not in i_req:
		return defaultValue
	val_str = i_req[i_token]

	if i_type == bool:
		res = defaultValue
		if val_str == "1" or val_str.lower() == "true":
			res = True
		elif val_str == "0" or val_str.lower() == "false":
			res = False
		return res
	elif i_type == int:
		try:
			res = int(val_str)
			return res
		except:
			return defaultValue
	else:
		# string
		return val_str

	return defaultValue


######################################################################


@application.route("/ssmon/api/v1/open", method=['POST'])
def OpenConnection():
	connection = Connection()
	connection.C = bottle.request.json

	for ipf in IP_FILTERS:
		if IpMatch(i_ip=connection['ip'], i_regexp=ipf):
			print("Filter out IP ", connection['ip'], ipf)
			return

	try:
		geoloc = IP2GeoLoc(connection['ip'], cfg()['GEOIP']['key'])
		if geoloc:
			connection['lat'] = geoloc['latitude']
			connection['lon'] = geoloc['longitude']
			connection['lon'] = geoloc['longitude']
			connection['country'] = geoloc['country_name']
			connection['city'] = geoloc['city']
	except:
		print(traceback.format_exc())
		print("Geo Location Failed")

	DB.OpenConnection(connection)

	notify_msg = 'Open {}#{} {}/{}'.format(
		connection['ip'], connection['server_instance'], connection['city'], connection['country'])
	for nr in G_NOTIFY_RECIPENTS:
		nr(notify_msg)

	# return connection updated with geolocation info
	bottle.response.content_type = "application/javascript"
	return connection.json()


@application.route("/ssmon/api/v1/close", method=['POST'])
def CloseConnection():
	connection = Connection()
	connection.C = (bottle.request.json)

	for ipf in IP_FILTERS:
		if IpMatch(i_ip=connection['ip'], i_regexp=ipf):
			print("Filter out IP ", connection['ip'], ipf)
			return

	notify_msg = 'Close {}#{} {}/{} @{}'.format(
		connection['ip'], connection['server_instance'],
		connection['city'], connection['country'],
		datetime.datetime.utcfromtimestamp(connection['duration']).strftime('%H:%M:%S'))

	DB.CloseConnection(connection)

	for nr in G_NOTIFY_RECIPENTS:
		nr(notify_msg)


######################################################################

# @application.route("/ssmon/api/v1/GetAll", method=['GET'])
# def GetAll():
#     bottle.response.content_type = "application/json"
#     res = DB.GetAll()
#     return JSONEncoder().encode(res)


@application.route("/ssmon/api/v1/GetConnectionCounts", method=['GET'])
def GetConnectionCounts():
	bottle.response.content_type = "application/json"
	res = DB.GetConnectionCounts()
	res['country'].sort(key=lambda x: x[1], reverse=True)
	res['city'].sort(key=lambda x: x[1], reverse=True)
	return JSONEncoder().encode(res)

@application.route("/ssmon/api/v1/active", method=['GET'])
def GetActive():
	bottle.response.content_type = "application/json"
	res = DB.GetConnectionCounts()['ACTIVE']
	return JSONEncoder().encode(res)

@application.route("/ssmon/api/v1/GetConnectionStats", method=['GET'])
def GetConnectionStats():
	bottle.response.content_type = "application/json"
	res = DB.GetConnectionStats()
	return JSONEncoder().encode(res)


@application.route("/ssmon/api/v1/country", method=['GET'])
def GetCountries():
	bottle.response.content_type = "application/json"
	res = DB.GetConnectionCounts()['country']
	res.sort(key=lambda x: x[1], reverse=True)
	return JSONEncoder().encode(res)


@application.route("/ssmon/api/v1/city", method=['GET'])
def GetCities():
	bottle.response.content_type = "application/json"
	res = DB.GetConnectionCounts()['city']
	res.sort(key=lambda x: x[1], reverse=True)
	return JSONEncoder().encode(res)


@application.route("/ssmon/api/v1/location", method=['GET'])
def GetLocations():
	bottle.response.content_type = "application/json"

	data = DB.GetConnectionCountsFull()
	data = data['ip']
	# data = [
	#     {'lat': x[8], 'lon': x[9], 'count': x[12], 'country': x[10], 'city': x[11]} for x in res
	# ]

	# multiple IPs will have the same lat/lon position from geolocation API
	# and will overlap on the map
	# therefore, accumulate connections count for each lat/lon point
	res = {}
	for d in data:
		try:
			lat_lon = (d[8], d[9])
			if lat_lon not in res:
				res[lat_lon] = {
					'count':    d[12],
					'city':     d[11],
					'country':  d[10],
					'lat': lat_lon[0],
					'lon': lat_lon[1]
				}
			else:
				res[lat_lon]['count'] += d[12]
		except:
			# print(d)
			pass

	res = list( res.values() )

	return JSONEncoder().encode(res)


@application.route('/static/<path:path>')
def server_static(path):
	return bottle.static_file(path, root='static')


@application.route("/")
def Root():
	return bottle.static_file('index.html', root='static')


######################################################################

def RUN(hostname="0.0.0.0",
		port=8080,
		debug=False,
		reloader=False):

	bottle.run(host=hostname, port=port, debug=debug, reloader=reloader)


def CurDir():
	d = os.path.dirname(sys.argv[0])
	if d == '' or d == '.':
		if 'PWD' in os.environ:
			d = os.environ['PWD']
		else:
			d = os.getcwd()
	return d


def main():

	# load config
	config_file = './user.ini'
	if len(sys.argv) > 1:
		config_file = sys.argv[1]
	cfg(config_file)
	pprint(cfg())
	print("\n")

	dbfile = cfg()['DB']['file']
	host = cfg()['DB']['ip']
	port = int( cfg()['DB']['port'] )

	global IP_FILTERS
	IP_FILTERS = cfg()['DB']['ip_filters']

	# notifiers
	global G_NOTIFY_RECIPENTS

	# G_NOTIFY_RECIPENTS = [ NotifySlack() ]
	# NotifySlack.NotifySlack() will not work with python < 3.6 - and armbian 5.7
	# therefore use system call to execute with python 2
	if 'SLACK' in cfg() and cfg()['SLACK']['use']:
		_key = cfg()['SLACK']['key']
		_chan = cfg()['SLACK']['channel']
		_cmd = './NotifySlack.py {} {} '.format(_key, _chan)
		G_NOTIFY_RECIPENTS.append( lambda msg: os.system(_cmd + msg) )
		print("Adding slack notifications on channel ", _chan)
		print("\n")


	print('{}:{} {}'.format(host, port, dbfile))
	print('@{}'.format(getpass.getuser()))
	print("IP Filters: ", IP_FILTERS)
	print("Current dir: ",CurDir())


	os.chdir(CurDir())

	global DB
	DB = ConnectionsDB(dbfile)
	RUN(host, port)


if __name__ == "__main__":
	try:
		import setproctitle
		setproctitle.setproctitle('SpyServerDB')
		print('SpyServerDB')
	except:
		pass

	main()
