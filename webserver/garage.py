import logging
from logging.handlers import RotatingFileHandler

import os
import sys
from flask import Flask, request, session, g, redirect, url_for, abort, \
     render_template, flash, jsonify, has_request_context, send_from_directory, send_file

from common import constants
from common.db import GarageDb
from common.iftt import IftttEvent
from common.telegram import TelegramNotification
from webserver.client_api import GaragePiClient
import time
import csv

# ------------- Setup ------------

# Create our application
app = Flask(__name__, instance_relative_config=True)

# Set up logging
app.logger_name = "WEBSRVR"
file_handler = RotatingFileHandler(os.path.join(app.instance_path, 'garage_webserver.log'),
                                   constants.LOGFILE_MODE, constants.LOGFILE_MAXSIZE,
                                   constants.LOGFILE_BACKUP_COUNT)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter(constants.LOGFILE_FORMAT))
app.logger.addHandler(file_handler)
app.debug_log_format = '%(relativeCreated)-6d [%(process)-5d:%(thread)#x] %(levelname)-5s %(message)s [in %(module)s @ %(pathname)s:%(lineno)d]'
app.logger.setLevel(logging.DEBUG)

# Log startup
app.logger.info('---------- Starting up!')
app.logger.info('__name__ is \'%s\'' % __name__)

# Load default config and override config from an environment variable
app.config.update(dict(
    RELAY_PIN=7,
    REED_PIN=18,
    DOOR_OPENED=None,  # 1 for open, 0 for closed
    NEED_CLEANUP=False,
    SECRET_KEY='',  # should be overwritten by your app config!
))

# Load configuration
resource_path = os.path.dirname(os.path.realpath(os.path.abspath(sys.argv[0]))) + os.sep + 'resource'
default_cfg_file = os.path.join(resource_path, 'default_app.cfg')
app.logger.debug('Loading default config file from \'%s\'' % default_cfg_file)
app.config.from_pyfile(default_cfg_file)
app.logger.debug('Looking for custom app config in \'%s\'' % os.path.join(app.instance_path, 'app.cfg'))
app.config.from_pyfile('app.cfg')
app.logger.debug('Loaded custom app config...')
api_trigger_key = app.config['API_TRIGGER_KEY']
replay_delay_seconds = app.config['REPLAY_DELAY_TIMER_SECONDS']
if not replay_delay_seconds: replay_delay_seconds = 30
show_timed_buttons1 = app.config['SHOW_TIMED_BUTTONS1']
show_timed_buttons2 = app.config['SHOW_TIMED_BUTTONS2']
show_timed_buttons1_text = app.config['SHOW_TIMED_BUTTONS1_TEXT']
show_timed_buttons2_text = app.config['SHOW_TIMED_BUTTONS2_TEXT']
timed_buttons1_seconds = app.config['TIMED_BUTTONS1_SECONDS']
timed_buttons2_seconds = app.config['TIMED_BUTTONS2_SECONDS']
timed_buttons1_seconds_3rd = app.config['TIMED_BUTTONS1_SECONDS_3RD']
timed_buttons2_seconds_3rd = app.config['TIMED_BUTTONS2_SECONDS_3RD']

app.logger.debug('Setup variables...')

# -------------- App Context Resources ----------------
def get_api_client() -> GaragePiClient:
    """
    Creates a new client api connector if there isn't one created
    yet for the current application context.
    """
    if not hasattr(g, 'api_client'):
        g.api_client = GaragePiClient(app.logger, app.config['IPC_PORT'])
    return g.api_client

def get_db() -> GarageDb:
    """
    Creates a new database connection if there is none yet for the
    current application context.
    """
    if not hasattr(g, 'sqlite_db'):
        g.sqlite_db = GarageDb(app.instance_path, resource_path)
    return g.sqlite_db


@app.teardown_appcontext
def close_db(error):
    """Closes the database again at the end of the request."""
    app.logger.debug("Tearing down app context")
    if hasattr(g, 'api_client'):
        app.logger.debug("Tearing down app context: closing api client")
        g.api_client.close()

# -------------- Routes ----------------
@app.route('/')
def show_control():
    app.logger.debug('Received request for /')
    session['show_timed_buttons1'] = show_timed_buttons1
    session['show_timed_buttons2'] = show_timed_buttons2
    session['show_timed_buttons1_text'] = show_timed_buttons1_text
    session['show_timed_buttons2_text'] = show_timed_buttons2_text
    session['timed_buttons1_seconds'] = timed_buttons1_seconds
    session['timed_buttons2_seconds'] = timed_buttons2_seconds
 
    return render_template('garage_control.html')

@app.route('/trigger', methods=['POST'])
def trigger_openclose():
    app.logger.debug('Received POST to trigger')
    if not session.get('logged_in'):
        app.logger.warning('Refusing to trigger relay because not logged in!')
        abort(401)
    app.logger.debug('Triggering relay')
    get_api_client().trigger_relay(request.headers.get('User-Agent') if has_request_context() else 'SERVER',
                                   app.config['USERNAME']);
    app.logger.debug('Relay triggered')
    flash('Relay successfully triggered')
    return redirect(url_for('show_control'))

@app.route('/crack', methods=['POST'])
def trigger_crack():
    app.logger.debug('Received POST to crack')
    if not session.get('logged_in'):
        app.logger.warning('Refusing to trigger relay because not logged in!')
        abort(401)
    app.logger.debug('Triggering relay')
    get_api_client().trigger_relay(request.headers.get('User-Agent') if has_request_context() else 'SERVER',
                                   app.config['USERNAME']);
    app.logger.debug('Relay triggered')
    flash('Relay successfully triggered')
    crack_delay = app.config['CRACK_DELAY']
    time.sleep(crack_delay)
    app.logger.debug('Triggering relay')
    get_api_client().trigger_relay(request.headers.get('User-Agent') if has_request_context() else 'SERVER',
                                   app.config['USERNAME']);
    app.logger.debug('Relay triggered')
    flash('Relay successfully triggered')
    return redirect(url_for('show_control'))

@app.route('/triggertimed', methods=['POST'])
def trigger_openclosetimed():
    app.logger.debug('Received POST to timed trigger')
    if not session.get('logged_in'):
        app.logger.warning('Refusing to timed trigger relay because not logged in!')
        abort(401)

    autoTime = replay_delay_seconds
    btn = int(request.form['btn'])
    newTime = float(request.form['time']) #request.args.get('time')
    if isinstance(newTime, float):
        if newTime > 0 and newTime <= 120:
            autoTime = newTime

    app.logger.debug('Triggering relay')
    get_api_client().trigger_relay(request.headers.get('User-Agent') if has_request_context() else 'SERVER',
                                   app.config['USERNAME'])
    app.logger.debug('Relay triggered')
    app.logger.debug('Waiting ' + str(autoTime) + ' seconds')
    time.sleep(autoTime)
    app.logger.debug('Triggering delayed relay ' + str(autoTime) + ' seconds')
    get_api_client().trigger_relay(request.headers.get('User-Agent') if has_request_context() else 'SERVER',
                                   app.config['USERNAME'])
    app.logger.debug('Relay delayed triggered')

    if (btn == 1):
      if (timed_buttons1_seconds_3rd > 0):
         time.sleep(timed_buttons1_seconds_3rd)
         get_api_client().trigger_relay(request.headers.get('User-Agent') if has_request_context() else 'SERVER',
                                   app.config['USERNAME'])
         app.logger.debug('Relay delayed 3rd triggered 9 - btn1')


    if (btn == 2):
      if (timed_buttons2_seconds_3rd > 0):
         time.sleep(timed_buttons2_seconds_3rd)
         get_api_client().trigger_relay(request.headers.get('User-Agent') if has_request_context() else 'SERVER',
                                   app.config['USERNAME'])
         app.logger.debug('Relay delayed 3rd triggered - btn2')

    flash('Relay successfully triggered')
    return redirect(url_for('show_control'))

@app.route('/triggerAPI' + api_trigger_key, methods=['GET', 'POST'])
def trigger_opencloseAPI():
    app.logger.debug('Received GET to triggerAPI')
    if not api_trigger_key: return 'No api_trigger_key setup!'

    app.logger.debug('Triggering API relay') 
    get_api_client().trigger_relay(request.headers.get('User-Agent') if has_request_context() else 'SERVER',
                                   app.config['USERNAME'])
    app.logger.debug('Relay API triggered')
    flash('Relay API successfully triggered')
    return redirect(url_for('show_control'))

@app.route('/triggerAPItimed' + api_trigger_key, methods=['GET', 'POST'])
def trigger_opencloseAPItimed():
    app.logger.debug('Received GET to triggerAPItimed')
    if not api_trigger_key: return 'No api_trigger_key setup!'

    autoTime = replay_delay_seconds
    newTime = float(request.form['time']) #request.args.get('time')
    if isinstance(newTime, float):
        if newTime > 0 and newTime <= 120:
            autoTime = newTime

    app.logger.debug('Triggering API timed relay')
    get_api_client().trigger_relay(request.headers.get('User-Agent') if has_request_context() else 'SERVER',
                                   app.config['USERNAME'])
    app.logger.debug('Waiting ' + str(autoTime) + ' seconds')
    time.sleep(autoTime)
    app.logger.debug('Triggering delayed API relay timed ' + str(autoTime) + ' seconds')
    get_api_client().trigger_relay(request.headers.get('User-Agent') if has_request_context() else 'SERVER',
                                   app.config['USERNAME'])
    app.logger.debug('Relay delayed triggered')
    flash('Relay API successfully triggered')
    return redirect(url_for('show_control'))


@app.route('/query_status')
def query_status() -> str:
    status = get_api_client().get_status()
    if status is None: return "{}"
    return jsonify(status)


def get_status():
    return get_api_client().get_status()


@app.route('/history')
def show_history():
    db = get_db()
    entries = db.read_history()
    return render_template('history.html', entries=entries)

@app.route('/full_history')
def show_full_history():
    db = get_db()
    entries = db.read_full_history()
    return render_template('full_history.html', entries=entries)

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        if request.form['username'] != app.config['USERNAME']:
            error = 'Invalid username'
        elif request.form['password'] != app.config['PASSWORD']:
            error = 'Invalid password'
        else:
            session['logged_in'] = True
            session.permanent = True
            flash('You were logged in')
            return redirect(url_for('show_control'))
    return render_template('login.html', error=error)


@app.route('/download')
def download():
    db = get_db()
    entries = db.read_full_history()
    filename = 'history.csv'
    with open(os.path.join(app.instance_path, filename),'w', newline='') as csv_file:
        wr = csv.writer(csv_file, quoting=csv.QUOTE_ALL)
        wr.writerow(["Time","Event","Description"])
        for row in entries:
            wr.writerow(row)
    try:
        return send_from_directory(os.path.join(app.instance_path), filename, as_attachment=True, attachment_filename=filename)
    except:
        abort(404)


@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    flash('You were logged out')
    return redirect(url_for('show_control'))


# ----- Tests --------

@app.route('/test_zmq')
def test_zmq():
    if not app.debug: return 'Only available when debug is set to True in application config.'

    msg = request.args.get('msg')

    app.logger.debug("Calling echo with message: {0}".format(msg))
    message = get_api_client().echo(msg)
    app.logger.debug("Returned from echo: {0}".format(message))

    if message is None: return "Received no reply!"
    return "Received reply [{0}]".format(message)

@app.route('/test_ifttt')
def test_ifttt():
    if not app.debug: return 'Only available when debug is set to True in application config.'

    maker_key = app.config['IFTTT_MAKER_KEY']
    if not maker_key: return 'No maker key provided!'

    event_name = request.args.get('event_name')
    # if not event_name: return redirect(url_for('show_control'), code=302)
    value1 = request.args.get('value1')
    value2 = request.args.get('value2')
    value3 = request.args.get('value3')
    app.logger.debug("Testing IFTTT with: %r %r %r %r" % (event_name, value1, value2, value3))

    event = IftttEvent(maker_key, request.args.get('event_name'), app.logger)
    result = event.trigger(value1, value2, value3)

    return 'Result: %r' % (result,)

@app.route('/test_telegram')
def test_telegram():
    if not app.debug: return 'Only available when debug is set to True in application config.'
    telegram_chat_id = str(app.config['APPRISE_TELEGRAM_CHAT_ID'])
    telegram_key = str(app.config['APPRISE_TELEGRAM_KEY'])
    if not telegram_key: return 'No Telegram key provided!'
    app.logger.debug("Testing Telegram with %s and %s" % (telegram_key,telegram_chat_id))

    event = TelegramNotification(telegram_key, telegram_chat_id, "Test notification from GaragePi", app.logger)
    event.trigger()
    return redirect(url_for('show_control'))