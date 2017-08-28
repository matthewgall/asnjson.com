#!/usr/bin/env python

import os, sys, argparse, logging, json, base64
import requests, redis
from functools import lru_cache
from bottle import route, request, response, redirect, default_app, view, template, static_file
from cymruwhois import Client

def set_content_type(fn):
	def _return_json(*args, **kwargs):
		response.headers['Content-Type'] = 'application/json'
		if request.method != 'OPTIONS':
			return fn(*args, **kwargs)
	return _return_json

def enable_cors(fn):
	def _enable_cors(*args, **kwargs):
		response.headers['Access-Control-Allow-Origin'] = '*'
		response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, OPTIONS'
		response.headers['Access-Control-Allow-Headers'] = 'Origin, Accept, Content-Type, X-Requested-With, X-CSRF-Token'

		if request.method != 'OPTIONS':
			return fn(*args, **kwargs)
	return _enable_cors

def return_error(status=404, message=''):
	log.error(message)
	output = {
		'success': False,
		'message': message
	}
	response.status = status
	return json.dumps(output)

@route('/get/<ip>', method=('OPTIONS', 'GET'))
@enable_cors
@set_content_type
@lru_cache(maxsize=32)
def process(ip):

	output = {
		"results": [],
		"results_info": {
			"count": 0,
			"cached": 0
		}
	}

	for ip in ip.split(','):
		if r.get(ip):
			output['results'].append(json.loads(r.get(ip)))
			output['results_info']['cached'] = output['results_info']['cached'] + 1
		else:
			try:
				data = Client().lookup(ip)
			except AttributeError:
				return return_error(400, "{} is not a valid IP address".format(ip))

			data = {
				"ip": ip,
				"asn": data.asn,
				"prefix": data.prefix,
				"owner": data.owner
			}

			# Now we push it to redis
			r.set(ip, json.dumps(data), ex=args.redis_ttl)
			output['results'].append(json.loads(r.get(ip)))

	output['results_info']['count'] = len(output['results'])
	return json.dumps(output)

@route('/cache')
@set_content_type
def cache():
	try:
		output = {}
		for key in r.scan_iter('*'):
			output[key.decode("utf-8")] = json.loads(r.get(key))['contacts']['abuse']
		return json.dumps(output)
	except:
		return return_error(403, "Unable to load keys from redis for display. Please try again later.")

@route('/ping')
def ping():
	response.content_type = "text/plain"
	return "pong"

@route('/')
def index():
	if request.query.q != "":
		return process(request.query.q)
	return "asnjson.com: Putting an IP address, to an ASN"

if __name__ == '__main__':

	parser = argparse.ArgumentParser()

	# Server settings
	parser.add_argument("-i", "--host", default=os.getenv('IP', '127.0.0.1'), help="server ip")
	parser.add_argument("-p", "--port", default=os.getenv('PORT', 5000), help="server port")

	# Redis settings
	parser.add_argument("--redis-host", default=os.getenv('REDIS_HOST', 'redis'), help="redis hostname")
	parser.add_argument("--redis-port", default=os.getenv('REDIS_PORT', 6379), help="redis port")
	parser.add_argument("--redis-pw", default=os.getenv('REDIS_PW', ''), help="redis password")
	parser.add_argument("--redis-ttl", default=os.getenv('REDIS_TTL', 60), help="redis time to cache records")

	# Verbose mode
	parser.add_argument("--verbose", "-v", help="increase output verbosity", action="store_true")
	args = parser.parse_args()

	if args.verbose:
		logging.basicConfig(level=logging.DEBUG)
	else:
		logging.basicConfig(level=logging.INFO)
	log = logging.getLogger(__name__)

	try:
		r = redis.Redis(
			host=args.redis_host,
			port=args.redis_port, 
			password=args.redis_pw,
		)
	except:
		log.error("Unable to connect to redis on {}:{}".format(args.redis_host, args.redis_port))

	try:
		app = default_app()
		app.run(host=args.host, port=args.port, server='tornado')
	except:
		log.error("Unable to start server on {}:{}".format(args.host, args.port))