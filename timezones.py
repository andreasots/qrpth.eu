from server import app

import flask
import requests
import pytz
import datetime

def timezone():
	res = requests.get("http://ip-api.com/json/{}".format(flask.request.remote_addr)).json()
	return res["timezone"]

NAME_OVERRIDE = {
    "America/Bahia_Banderas": "Bahia de Banderas",
    "Antarctica/DumontDUrville": "Dumont-d'Urville",
    "Asia/Sakhalin": "Yuzhno-Sakhalinsk",
}

def zone_name(zone):
    if zone in NAME_OVERRIDE:
        # Hurr-durr 14-character restrictions
        zonename = NAME_OVERRIDE[zone]
    else:
        # Undo some the transformations the IANA database does
        zonename = zone.split('/', 1)[1]
        zonename = ", ".join(zonename.split('/')[::-1])
        zonename = zonename.replace('_', ' ')
    return zone, zonename

def timezones():
    for cc, name in sorted(pytz.country_names.items(), key=lambda e: e[1]):
        yield name, map(zone_name, pytz.country_timezones.get(cc, []))

def local_time(zone):
	try:
		zone = pytz.timezone(zone)
		return datetime.datetime.now(zone)
	except:
		return None

@app.route("/timezone")
def view():
	if "timezone" in flask.request.args:
		zone = flask.request.args["timezone"]
		name = zone_name(zone)
		return flask.render_template("timezone.html", page="tz", timezones=timezones(), timezone=zone, now=local_time(zone), zone_name=name[1])
	if "no_js" in flask.request.args:
		return flask.redirect("/timezone?timezone={}".format(timezone()))
	return flask.render_template("timezone.html", page="tz", timezones=timezones())
