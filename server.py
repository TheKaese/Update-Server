import logging
import os
import os.path
import re
from datetime import datetime
from logging.handlers import RotatingFileHandler
from os import path

import yaml
from flask import Flask, request, render_template, flash, redirect, url_for, send_from_directory
from packaging import version

APP_UPLOAD_FOLDER = '/etc/UpdateServer/bin'
LOG_FOLDER = '/var/log/UpdateServer'

os.makedirs(APP_UPLOAD_FOLDER, exist_ok=True)
os.makedirs(LOG_FOLDER, exist_ok=True)

MAC_HEADER_ESP8266 = 'X_ESP8266_STA_MAC'
MAC_HEADER_ESP32 = 'x_ESP32_STA_MAC'

ALLOWED_EXTENSIONS = {'bin'}

ARG_PLATFORM = 'platform'
ARG_VERSION = 'version'
ARG_BIN_FILE = 'bin_file'
ARG_SPIFFS_FILE = 'spiffs_file'
ARG_NAME = 'name'
ARG_UPLOADED = 'uploaded'
ARG_BIN_DOWNLOADS = 'bin_downloads'
ARG_SPIFFS_DOWNLOADS = 'spiffs_downloads'

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = APP_UPLOAD_FOLDER
app.config['SECRET_KEY'] = 'lkj3e/a90-12hnalas487543zxj3'

PLATFORMS_YAML = APP_UPLOAD_FOLDER + '/platforms.yml'

logFormatter = logging.Formatter("%(asctime)s [%(threadName)-12.12s] [%(levelname)-5.5s]  %(message)s")
logger = logging.getLogger('updater_logger')
logger.setLevel(logging.DEBUG)

handler = RotatingFileHandler(LOG_FOLDER + "/updater.log", maxBytes=2000, backupCount=10)
handler.setFormatter(logFormatter)
logger.addHandler(handler)

handler = logging.StreamHandler()
handler.setFormatter(logFormatter)
logger.addHandler(handler)

globalPlats = None


def load_config():
    global globalPlats
    if globalPlats is None:
        logger.debug("Reloading global platform cache")

        if not path.exists(PLATFORMS_YAML):
            return globalPlats

        try:
            with open(PLATFORMS_YAML, 'r') as stream:
                globalPlats = yaml.load(stream, Loader=yaml.FullLoader)
        except yaml.YAMLError as err:
            print(err)
            flash(err)
        except Exception as e:
            print(e)
            flash('Error: File not found.')

    return globalPlats


def save_config(platforms):
    global globalPlats
    try:

        if not path.exists(APP_UPLOAD_FOLDER):
            os.mkdir(APP_UPLOAD_FOLDER)

        with open(PLATFORMS_YAML, 'w') as outfile:
            yaml.dump(platforms, outfile, default_flow_style=False)

            # reload the config
            globalPlats = None
            load_config()

            return True

    except Exception as e:
        logger.debug(e)
        flash('Error: Data not saved.')
    return False


def load_request():
    if MAC_HEADER_ESP8266 in request.headers:
        __mac = request.headers[MAC_HEADER_ESP8266]
        __mac = str(re.sub(r'[^0-9A-fa-f]+', '', __mac.lower()))
        logger.debug("INFO: Update called by ESP8266 with MAC " + __mac)
    elif MAC_HEADER_ESP32 in request.headers:
        __mac = request.headers[MAC_HEADER_ESP32]
        __mac = str(re.sub(r'[^0-9A-fa-f]+', '', __mac.lower()))
        logger.debug("INFO: Update called by ESP32 with MAC " + __mac)
    else:
        __mac = ''
        logger.debug("WARN: Update called without known headers.")

    client_plat = request.args.get(ARG_PLATFORM, default=None)
    client_ver = request.args.get(ARG_VERSION, default=None)

    if not client_plat or not client_ver:
        logger.debug("ERROR: Invalid parameters.")
        return 'Error: Invalid parameters.', 400

    client_ver = client_ver.lower()
    client_ver = client_ver.replace('v', '')

    return client_plat, client_ver, __mac


@app.route('/update/bin', methods=['GET', 'POST'])
def update_bin():
    client_plat, client_ver, client_mac = load_request()
    platforms = load_config()

    logger.debug("INFO: Client Plat: '" + client_plat + "' Client Ver: " + client_ver)

    if not platforms:
        logger.debug("ERROR: No platforms currently exist, create a platform before updating.")
        return 'Error: No platforms currently exist, create a platform before updating.', 404

    if client_plat not in platforms.keys():
        logger.debug("ERROR: Unknown platform.")
        return 'Error: Unknown platform.', 404

    for server_ver in platforms[client_plat]:

        if not version.parse(client_ver) < version.parse(server_ver):
            continue

        if os.path.isfile(app.config[APP_UPLOAD_FOLDER] + '/' + platforms[client_plat][server_ver][ARG_BIN_FILE]):
            platforms[client_plat][server_ver][ARG_BIN_DOWNLOADS] += 1
            save_config(platforms)
            return send_from_directory(directory=app.config[APP_UPLOAD_FOLDER],
                                       filename=platforms[client_plat][server_ver][ARG_BIN_FILE],
                                       as_attachment=True, mimetype='application/octet-stream',
                                       attachment_filename=platforms[client_plat][server_ver][ARG_BIN_FILE])

    return 'No update needed.', 304


@app.route('/update/spiffs', methods=['GET', 'POST'])
def update_spiffs():
    client_plat, client_ver, client_mac = load_request()
    platforms = load_config()

    logger.debug("INFO: Client Plat: '" + client_plat + "' Client Ver: " + client_ver)

    if not platforms:
        logger.debug("ERROR: No platforms currently exist, create a platform before updating.")
        return 'Error: No platforms currently exist, create a platform before updating.', 404

    if client_plat not in platforms.keys():
        logger.debug("ERROR: Unknown platform.")
        return 'Error: Unknown platform.', 404

    for server_ver in platforms[client_plat]:

        if not version.parse(client_ver) < version.parse(server_ver):
            continue

        if os.path.isfile(app.config[APP_UPLOAD_FOLDER] + '/' + platforms[client_plat][server_ver][ARG_SPIFFS_FILE]):
            platforms[client_plat][server_ver][ARG_SPIFFS_DOWNLOADS] += 1
            save_config(platforms)
            return send_from_directory(directory=app.config[APP_UPLOAD_FOLDER],
                                       filename=platforms[client_plat][server_ver][ARG_SPIFFS_FILE],
                                       as_attachment=True, mimetype='application/octet-stream',
                                       attachment_filename=platforms[client_plat][server_ver][ARG_SPIFFS_FILE])

    return 'No update needed.', 304


def validate_file_extension(filename):
    return '.' in filename \
           and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/upload', methods=['GET', 'POST'])
def upload():
    platforms = load_config()

    # GET
    if not request.method == 'POST':
        if platforms:
            return render_template('upload.html')
        flash("Create platforms before attempting to upload a file.")
        return render_template('status.html', platforms=platforms)

    # POST
    if ARG_BIN_FILE not in request.files:
        flash('Error: No request_bin_file selected.')
        return redirect(request.url)

    request_bin_file = request.files[ARG_BIN_FILE]
    if not request_bin_file or request_bin_file.filename == '':
        flash('Error: No request_bin_file selected.')
        return redirect(request.url)

    bin_file_name = request_bin_file.filename
    if not validate_file_extension(bin_file_name):
        flash('Error: File type not allowed "' + bin_file_name + '"')
        return redirect(request.url)

    file_version = re.search(b'v\\d+\\.\\d+(\\.\\d+)*', bin_file_name.encode('UTF-8'), re.IGNORECASE)
    if not file_version:
        flash('Error: No version found in "' + bin_file_name + '" not uploaded.')
        return redirect(request.url)

    request_spiffs_file = request.files[ARG_SPIFFS_FILE]
    if request_spiffs_file:
        spiffs_file_name = request_spiffs_file.filename
        if not validate_file_extension(spiffs_file_name):
            flash('Error: File type not allowed "' + spiffs_file_name + '"')
            return redirect(request.url)

        spiffs_file_version = re.search(b'v\\d+\\.\\d+(\\.\\d+)*', spiffs_file_name.encode('UTF-8'), re.IGNORECASE)
        if not spiffs_file_version:
            flash('Error: No version found in "' + spiffs_file_name + '".')
            return redirect(request.url)

        if not file_version == request_spiffs_file:
            flash('Error: BIN file "' + bin_file_name +
                  '" and SPIFFS file "' + spiffs_file_name + '" versions do not match.')
            return redirect(request.url)

    for platform in platforms.keys():

        if not re.search(platform.encode('UTF-8'), bin_file_name.encode('UTF-8'), re.IGNORECASE):
            flash('Error: No platform found in "' + bin_file_name + '" ("' + platform + '")')
            continue

        file_version = file_version.group()[1:].decode('utf-8')
        filename = platform + '_' + file_version.replace('.', '_')

        if file_version in platforms[platform]:
            flash('Error: No platform found in "' + bin_file_name + '" ("' + platform + '")')
            return redirect(request.url)

        request_bin_file.seek(0)
        request_bin_file.save(os.path.join(app.config[APP_UPLOAD_FOLDER], filename + ".bin"))
        request_bin_file.close()

        if request_spiffs_file:
            request_spiffs_file.seek(0)
            request_spiffs_file.save(os.path.join(app.config[APP_UPLOAD_FOLDER], filename + ".spiffs.bin"))
            request_spiffs_file.close()

        platforms[platform][file_version] = dict()
        platforms[platform][file_version][ARG_BIN_DOWNLOADS] = 0
        platforms[platform][file_version][ARG_SPIFFS_DOWNLOADS] = 0
        platforms[platform][file_version][ARG_BIN_FILE] = filename
        platforms[platform][file_version][ARG_UPLOADED] = datetime.now().strftime('%Y-%m-%d')

        if 'v0.0' in platforms[platform]:
            del platforms[platform]['v0.0']

        if save_config(platforms):
            flash('Success: File uploaded.')
        else:
            flash('Error: Could not save "' + bin_file_name + '".')

        return redirect(url_for('index'))

    flash('Error: No known platform name found in "' + bin_file_name + '". File not uploaded.')
    return redirect(request.url)


def validate_platform_name(name) -> bool:
    if not name:
        return False
    return True


@app.route('/create', methods=['GET'])
def create():
    platforms = load_config()

    if platforms:
        return render_template('update.html', names=platforms.keys())
    return render_template('update.html')


@app.route('/create', methods=['POST'])
def update():
    platforms = load_config()
    platform = request.form[ARG_NAME]

    if not validate_platform_name(platform):
        flash('Error: Invalid platform name.')
        return redirect(request.url)

    if not platforms:
        platforms = dict()

    if platform not in platforms:
        platforms[platform] = dict()

    platforms[platform]['v0.0'] = {ARG_BIN_FILE: None,
                                   ARG_UPLOADED: None,
                                   ARG_BIN_DOWNLOADS: 0,
                                   ARG_SPIFFS_DOWNLOADS: 0}

    if save_config(platforms):
        flash('Success: Platform created.')
        logger.debug("Created platform '%s'", platform)
    else:
        flash('Error: Could not save file.')
        logger.debug("Failed to create platform '%s'", platform)

    return render_template('status.html', platforms=platforms)


@app.route('/delete', methods=['POST'])
def delete():
    # POST
    __plat = request.form[ARG_NAME]
    if not validate_platform_name(__plat):
        flash('Error: Invalid name.')
        return redirect(request.url)

    platforms = load_config()
    if platforms and __plat in platforms.keys():
        del platforms[__plat]
        if save_config(platforms):
            flash('Success: Platform deleted.')
        else:
            flash('Error: Could not save file.')

    return render_template('status.html', platforms=platforms)


@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')


@app.route('/')
def status():
    platforms = load_config()
    return render_template('status.html', platforms=platforms)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int('5000'), debug=False)
