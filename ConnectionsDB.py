#!/usr/bin/env python3

import string
import os
import datetime
import sqlite3
import threading
import json
import traceback
import inspect

from sqlite3 import Error as sqerr
from pprint import pprint, pformat


class JSONEncoder(json.JSONEncoder):
	def default(self, o):
		if isinstance(o, datetime.datetime):
			return str(o)
		return json.JSONEncoder.default(self, o)

class Connection:
	'''
	Some simple struct keeping connection IP, time and some other info.
	Passed over http and internally.
	'''
	C = {}
	def __init__(self, _c=None):
		if _c:
			self.C = _c
		else:
			_now = datetime.datetime.utcnow()
			self.C = {
				'ip': '0.0.0.0',
				'port': '0',
				'server_instance': '', # use spyserver config filename
				'sdr_version': '',
				'os': '',
				'start': _now,
				'end': None #_now
			}

	def __hash__(self):
		return hash( self.C['ip'] + ':' + self.C['port'] + '#' + self.C['server_instance'] )

	def __eq__(self, b):
		return self.__hash__() == b.__hash__()

	def __getitem__(self, key):
		if key in self.C:
			return self.C[key]
		return None

	def __setitem__(self, key, value):
		self.C[key] = value

	def __contains__(self, key):
		return key in self.C

	def __str__(self):
		return pformat(self.C)

	def __repr__(self):
		return pformat(self.C)

	def json(self, _in = None):
		if _in:
			self.C = json.loads(_in)
			# parse datetime objects
			if 'start' in self.C:
				self.C['start'] = datetime.datetime.strptime(self.C['start'], '%Y-%m-%d %H:%M:%S.%f')
			if 'end' in self.C and self.C['end']:
				self.C['end'] = datetime.datetime.strptime(self.C['end'], '%Y-%m-%d %H:%M:%S.%f')
		else:
			return JSONEncoder().encode(self.C)


class ConnectionsDB():
	'''
	store connections in sqlite DB
	'''
	def __init__(self, sqldb_file):
		self.__sqldb = None
		self.__sqldb_file = sqldb_file
		self.__mutex = threading.Lock()
		self.__initSQLDB()
		self.__active_connections = [] # opened connections
		self.__active_connections_per_srv_instance = {} # opened connections per server_instance

	def __initSQLDB(self):
		if self.__sqldb:
			return
		self.__sqldb = sqlite3.connect(
						self.__sqldb_file,
						check_same_thread=False,
						detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES )
		self.__createConnectionsTable()

	def __createConnectionsTable(self):
		_tb_cr = "CREATE TABLE IF NOT EXISTS connections ("
		_tb_cr += "	ip text,"
		_tb_cr += "	port text,"
		_tb_cr += "	server_instance text,"
		_tb_cr += "	sdr_version text,"
		_tb_cr += "	os text,"
		_tb_cr += "	start timestamp,"
		_tb_cr += "	end timestamp,"
		_tb_cr += "	duration real,"
		_tb_cr += "	lat real,"
		_tb_cr += "	lon real,"
		_tb_cr += "	country text,"
		_tb_cr += "	city text,"
		_tb_cr += " PRIMARY KEY(ip, port, server_instance, start)"
		_tb_cr += ");"

		try:
			with self.__mutex:
				cur = self.__sqldb.cursor()
				cur.execute(_tb_cr)
				self.__sqldb.commit()
		except sqerr as e:
			print(inspect.currentframe().f_lineno)
			print(e)
			print(traceback.format_exc())
		except:
			print(inspect.currentframe().f_lineno)
			print(traceback.format_exc())

	def OpenConnection(self, c):
		'''
		count opened connection
		'''
		if c not in self.__active_connections:
			self.__active_connections.append(c)

		if c['server_instance'] not in self.__active_connections_per_srv_instance:
			self.__active_connections_per_srv_instance[ c['server_instance'] ] = []
		self.__active_connections_per_srv_instance[ c['server_instance'] ].append(c)

		sql_insert = "INSERT INTO connections('ip', 'port', 'server_instance', 'sdr_version', 'os', 'start')\n"
		sql_insert += "VALUES(?,?,?,?,?,?);"
		data = ( c['ip'], c['port'], c['server_instance'], c['sdr_version'] , c['os'] , c['start'] )

		try:
			with self.__mutex:
				cur = self.__sqldb.cursor()
				cur.execute(sql_insert, data)
				self.__sqldb.commit()
		except sqlite3.IntegrityError:
			print(inspect.currentframe().f_lineno)
			print("already inserted")
		except sqerr as e:
			print(inspect.currentframe().f_lineno)
			print(e)

		# update GPS
		#
		if 	'lat' in c and 'lon' in c and 'city' in c and 'country' in c:
			sql_upd = "UPDATE connections\n"
			sql_upd += "SET\n"
			sql_upd += "\tlat = ?,\n"
			sql_upd += "\tlon = ?,\n"
			sql_upd += "\tcountry = ?,\n"
			sql_upd += "\tcity = ?\n"
			sql_upd += "WHERE\n"
			sql_upd += '\tip = ? AND'
			sql_upd += '\tport = ? AND'
			sql_upd += '\tserver_instance = ? AND'
			sql_upd += '\tstart = ?'

			data = ( c['lat'], c['lon'], c['country'], c['city'],
					c['ip'], c['port'], c['server_instance'], c['start'] )

			try:
				with self.__mutex:
					cur = self.__sqldb.cursor()
					cur.execute(sql_upd, data)
					self.__sqldb.commit()
			except sqlite3.IntegrityError:
				print(inspect.currentframe().f_lineno)
				print("already inserted")
			except sqerr as e:
				print(inspect.currentframe().f_lineno)
				print(e)
			except:
				print(inspect.currentframe().f_lineno)
				print(traceback.format_exc())


	def CloseConnection(self, c):
		'''
		update connection with end time/duration
		'''

		if c in self.__active_connections:
			self.__active_connections.remove(c)

		if c['server_instance'] not in self.__active_connections_per_srv_instance:
			self.__active_connections_per_srv_instance[ c['server_instance'] ] = []
		if c in self.__active_connections_per_srv_instance[ c['server_instance'] ]:
			self.__active_connections_per_srv_instance[ c['server_instance'] ].remove(c)

		sql_upd = "UPDATE connections\n"
		sql_upd += "SET end = ?,\n"
		sql_upd += "\tduration = ?\n"
		sql_upd += "WHERE\n"
		sql_upd += '\tip = ? AND'
		sql_upd += '\tport = ? AND'
		sql_upd += '\tserver_instance = ? AND'
		sql_upd += '\tstart = ?'

		data = ( c['end'], c['duration'],
				c['ip'], c['port'], c['server_instance'], c['start'] )
		try:
			with self.__mutex:
				cur = self.__sqldb.cursor()
				cur.execute(sql_upd, data)
				self.__sqldb.commit()
		except sqlite3.IntegrityError:
			print(inspect.currentframe().f_lineno)
			print("already inserted")
		except sqerr as e:
			print(inspect.currentframe().f_lineno)
			print(e)

	def GetAll(self):
		try:
			res = {}
			with self.__mutex:
				cur = self.__sqldb.cursor()
				_q = "SELECT * from connections"
				cur.execute(_q)
				res = cur.fetchall()
				return res
			return res

		except sqerr as e:
			print(inspect.currentframe().f_lineno)
			print(e)

	def GetConnectionCounts(self):
		try:
			res = {}
			with self.__mutex:
				cur = self.__sqldb.cursor()

				# count per key
				keys = ['server_instance', 'country', 'city', 'ip']
				for k in keys:
					_q = "SELECT {0}, COUNT({0}) from connections GROUP by {0}".format(k)
					cur.execute(_q)
					tmp = cur.fetchall()
					if tmp:
						res[k] = tmp

				# TOTAL
				_q = "SELECT COUNT(*) from connections"
				cur.execute(_q)
				tmp = cur.fetchone()
				if tmp:
					res['TOTAL'] = tmp[0]

			res['ACTIVE'] = {}
			res['ACTIVE']['TOTAL'] =  len(self.__active_connections)
			res['ACTIVE']['SERVER'] = {}
			for srv_inst in self.__active_connections_per_srv_instance:
				res['ACTIVE']['SERVER'][srv_inst] = self.__active_connections_per_srv_instance[srv_inst]

			# hash IPs :)
			for i in range( len(res['ip']) ):
				res['ip'][i] = ( hash(res['ip'][i][0]), res['ip'][i][1] )

			return res

		except sqerr as e:
			print(inspect.currentframe().f_lineno)
			print(e)

	def GetConnectionCountsFull(self):
		try:
			res = {}
			with self.__mutex:
				cur = self.__sqldb.cursor()


				# count per key
				keys = ['server_instance', 'country', 'city', 'ip']
				for k in keys:
					_q = "SELECT *, COUNT({0}) from connections GROUP by {0}".format(k)
					cur.execute(_q)
					tmp = cur.fetchall()
					if tmp:
						res[k] = tmp

				# TOTAL
				_q = "SELECT COUNT(*) from connections"
				cur.execute(_q)
				tmp = cur.fetchone()
				if tmp:
					res['TOTAL'] = tmp[0]

			res['ACTIVE'] = {}
			res['ACTIVE']['TOTAL'] =  len(self.__active_connections)
			res['ACTIVE']['SERVER'] = {}
			for srv_inst in self.__active_connections_per_srv_instance:
				res['ACTIVE']['SERVER'][srv_inst] = self.__active_connections_per_srv_instance[srv_inst]

			# hash IPs :)
			for i in range( len(res['ip']) ):
				_t = list( res['ip'][i] )
				_t[0] = hash(_t[0])
				res['ip'][i] = _t

			return res

		except sqerr as e:
			print(inspect.currentframe().f_lineno)
			print(e)

	def GetConnectionStats(self):
		'''
		longest
		most frequent IP
		average duration
		'''

		try:
			with self.__mutex:
				cur = self.__sqldb.cursor()

				res = {}

				# longest
				_q = 'SELECT * FROM connections ORDER BY duration DESC'
				cur.execute(_q)
				tmp = cur.fetchone()
				if tmp:
					res['longest'] = list( tmp )
					res['longest'][0] = hash(res['longest'][0])

				# most frequent ***
				_q_template = r'''	SELECT {0},
			 						COUNT({0}) AS value_occurrence
									FROM connections
									GROUP BY {0}
									ORDER BY value_occurrence DESC
									LIMIT    1;'''

				frequents = ['ip', 'country', 'city']
				for column in frequents:
					cur.execute( _q_template.format(column) )
					tmp = cur.fetchone()
					if tmp:
						res[column] = list( tmp )

				# average duration
				cur.execute('SELECT AVG(duration) FROM connections')
				tmp = cur.fetchone()
				if tmp:
					res['avg'] = tmp[0]

				# sum duration
				cur.execute('SELECT SUM(duration) FROM connections')
				tmp = cur.fetchone()
				if tmp:
					res['sum'] = tmp[0]

				# hash IP	 :)
				res['ip'] = ( hash(res['ip'][0]), res['ip'][1] )

				return res

		except sqerr as e:
			print(inspect.currentframe().f_lineno)
			print(e)
