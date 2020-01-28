#!/usr/bin/env python2

'''
slack for python3 requires python >= 3.6
which is not available on armbian 5.7

therefore this script can work for both python2 and python3
and defaults to python2 when run as standalone command
'''

import os
import sys

class NotifySlack:
	def __init__(self, api_key, channel):
		self.__key = api_key
		self.__channel = channel

		self.__py_version = 2
		_v = sys.version_info
		if _v.major >= 3 and _v.minor >= 6:
			self.__py_version = 3


	def Notify(self, msg):
		if self.__py_version == 3:
			try:
				from slack import WebClient
				self.__slack_version = 1
			except ImportError:
				print("SLACK API py3 unavailable.")
				return
		elif self.__py_version == 2:
			try:
				from slackclient import SlackClient
			except ImportError:
				print("SLACK API py2 unavailable.")
				return

		try:
			if self.__py_version == 3:
				sc = WebClient(self.__key)
				sc.chat_postMessage(channel=self.__channel, text=msg, username='wintermute')
			elif self.__py_version == 2:
				sc = SlackClient(self.__key)
				sc.api_call("chat.postMessage", channel=self.__channel, text=msg, username='wintermute')
		except:
			print("Unable to send slack notification!")
			import traceback
			print(traceback.format_exc())

if __name__ == "__main__":
	api_key = sys.argv[1]
	channel =sys.argv[2]
	msg = ' '.join(sys.argv[3:])

	ns = NotifySlack( api_key, channel )
	ns.Notify( msg )
