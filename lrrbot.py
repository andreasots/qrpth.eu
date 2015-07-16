from server import app

import psycopg2
import flask
import random

CONN = "postgres:///lrrbot"

def response(command, section):
    with psycopg2.connect(CONN) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT jsondata->%s->'response' FROM history WHERE section = %s ORDER BY historykey DESC LIMIT 1", (command, section))
            for responses, in cur:
                if isinstance(responses, list):
                    return random.choice(responses)
                return responses

@app.route("/!<command>")
def plain(command):
    return flask.Response(response(command, "responses"), content_type="text/plain")

@app.route("/!explain <command>")
def explain(command):
    return flask.Response(response(command, "explanations"), content_type="text/plain")
