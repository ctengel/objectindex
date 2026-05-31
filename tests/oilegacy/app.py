"""Object Index RESTful API"""

import flask


# Create the Flask application and the Flask-SQLAlchemy object.
app = flask.Flask(__name__)
app.config.from_envvar('OBJIDX_SETTINGS')


#if __name__ == '__main__':
#    app.run()
