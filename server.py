import flask, sys

app = flask.Flask(__name__)

if __name__ == '__main__':
	sys.modules['server'] = sys.modules['__main__']

import simple
import timezones
import prism
import lrrbot

if __name__ == '__main__':
	app.run(debug=True, host="0.0.0.0")
else:
	import logging
	app.logger.addHandler(logging.StreamHandler())
