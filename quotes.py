from server import app
import findquote 

import flask
import psycopg2

@app.route("/quotes")
def quotes():
    query = flask.request.args.get("q")
    if query is None or query.strip() == "":
        return flask.render_template("quotes.html", query="", quotes=[])
    where_clause = findquote.Parser(query).parse().to_sql()
    with psycopg2.connect("postgres:///lrrbot") as conn:
        with conn.cursor() as cur:
            print(where_clause)
            cur.execute("SELECT qid, quote, attrib_name, attrib_date FROM quotes WHERE %s" % where_clause)
            return flask.render_template("quotes.html", query=query, quotes=list(cur))

