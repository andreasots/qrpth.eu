from server import app

import flask

@app.route("/")
def index():
	return flask.render_template("index.html", page="index")
