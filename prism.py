from server import app

import datetime
import psycopg2
import flask
import pytz
import re

TIMEZONE = pytz.timezone("America/Vancouver")
CONN = "postgres:///lrrbot"

def convert_timezone(row):
    return (row[0], row[1], TIMEZONE.normalize(row[2].astimezone(TIMEZONE)))

@app.route("/prism/")
def prism():
    with psycopg2.connect(CONN) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT MIN(time) FROM log")
            start = next(iter(cur))[0]
            start = TIMEZONE.localize(datetime.datetime(start.year, start.month, start.day))
            
            stop = datetime.datetime.now(TIMEZONE)
            stop = TIMEZONE.localize(datetime.datetime(stop.year, stop.month, stop.day, 23, 59, 59)) + datetime.timedelta(seconds=1)
            
            days = []
            while start < stop:
                days += [(start, start+datetime.timedelta(days=1))]
                start += datetime.timedelta(days=1)
            return flask.render_template("prism.html", page="prism", days=days)

@app.route("/prism/log")
def logs():
    start = datetime.datetime.fromtimestamp(float(flask.request.args["start"]), pytz.utc)
    stop = datetime.datetime.fromtimestamp(float(flask.request.args["stop"]), pytz.utc)
    with psycopg2.connect(CONN) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, messagehtml, time FROM log WHERE target = '#loadingreadyrun' AND time BETWEEN %s AND %s ORDER BY TIME", (start, stop))
            return flask.render_template("prism-log.html", page="prism", messages=map(convert_timezone, cur))

@app.route("/prism/search")
def search():
    query = flask.request.args["q"]
    with psycopg2.connect(CONN) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, messagehtml, time, TS_RANK_CD(TO_TSVECTOR('english', message), query) AS rank
                FROM log, PLAINTO_TSQUERY('english', %s) query
                WHERE TO_TSVECTOR('english', message) @@ query
                ORDER BY rank DESC
            """, (query, ))
            return flask.render_template("prism-search.html", page="prism", messages=map(convert_timezone, cur), query=query)
