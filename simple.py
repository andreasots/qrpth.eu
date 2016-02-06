from server import app

import flask

@app.route("/")
def index():
	return flask.render_template("index.html", page="index")

@app.route("/patreon")
def patreon_docs():
	return flask.render_template("patreon.html")
