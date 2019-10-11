import os
import sys
import time
from datetime import datetime
import json
import logging
from functools import wraps

import redis
import base64
from logging.handlers import RotatingFileHandler
from flask import Flask, abort, flash, redirect, render_template, request, url_for, jsonify, send_file, Response

from waitress import serve


app = Flask(__name__)
app.config.from_pyfile('config_file.cfg')

redis_db = redis.StrictRedis(host=app.config["REDIS_HOST"], port=app.config["REDIS_PORT"], db=0)

ANNOTATORS = app.config['ANNOTATORS']
APP_URL = app.config['SCHEME'] + '://' + app.config['HOST'] + ':' + app.config['PORT']


def set_logger():
    formatter = logging.Formatter(fmt='%(asctime)s %(levelname)-8s %(message)s',
                                  datefmt='%Y-%m-%d %H:%M:%S')
    app_handler = RotatingFileHandler('annotation.log', maxBytes=9e9, backupCount=1)
    app_handler.setLevel(logging.INFO)
    app_handler.setFormatter(formatter)
    app.logger.addHandler(app_handler)
    werk_handler = RotatingFileHandler('flask_server.log', maxBytes=9e9, backupCount=1)
    logging.getLogger("werkzeug").addHandler(werk_handler)

def create_folder_structure():
    '''
    Create folder structure in static folder for annotation.
    '''
    for annotator in ANNOTATORS:
        image_dir = os.path.join(app.static_folder, 'images/' + annotator)
        if not os.path.exists(image_dir):
            app.logger.warn("creating image dir %s" % image_dir)
            os.makedirs(image_dir)

def get_image_url_list(annotator):
    '''
    Return a list of URIs for the images.
    '''
    image_path = os.path.join(app.static_folder, 'images/' + annotator)
    if os.path.exists(image_path):
        files = os.listdir(image_path)
        files = [f for f in files if f[0] != "."] # to avoid the .gitignore
        print (files)
        return sorted([APP_URL + '/static/images/{}/{}'.format(annotator, f) for f in files])
    else:
        app.logger.error('image_path:%s doesn\'t exist', image_path)
        return []

def get_annotation(image_url, user):
    '''
    Return annotation for the image from redis
    '''
    rkey = "{}-{}.json".format(user, image_url.split("/")[-1].split(".")[0])
    raw_json = redis_db.get(rkey)
    if raw_json:
        return json.loads(raw_json.decode("utf8"))
    return {}
    
def get_boxed_image_urls(image_url_list, user):
    '''
    Return subset of images for which boxes have been drawn.
    '''
    boxed_images = []
    for image in image_url_list:
        data = get_annotation(image, user)
        for key, value in data.items():
            if (len(value["regions"])):
                boxed_images.append(image)
    return boxed_images

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated

def check_auth(username, password):
    """This function is called to check if a username /
    password combination is valid.
    """
    return password == app.config["PASSWORD"]

def authenticate():
    """Sends a 401 response that enables basic auth"""
    return Response(
    'Could not verify your access level for that URL.\n'
    'You have to login with proper credentials', 401,
    {'WWW-Authenticate': 'Basic realm="Login Required"'})


@app.route("/<user>", defaults={"subset": None})
@app.route("/<user>/<int:subset>")
@app.route("/<user>/unboxed/<int:subset>")
@app.route("/<user>/boxed/<int:subset>")
@requires_auth
def home(user, subset):
    if user in ANNOTATORS:
        image_url_list = get_image_url_list(user)
        if subset is not None:
            image_url_list = image_url_list[(subset - 1) * 100 : (subset - 1) * 100 + 100]
        if 'boxed' in request.path:
            boxed_image_url_list = get_boxed_image_urls(image_url_list, user)
            if 'unboxed' in request.path:
                image_url_list = list(set(image_url_list) - set(boxed_image_url_list))
            else:
                image_url_list = boxed_image_url_list

        if not image_url_list:
            app.logger.error('Image list not obtained for user:%s', user)

        return render_template('via.html', annotator=user, image_list=image_url_list,
                               flask_app_url=APP_URL)
    else:
        app.logger.error('User:%s not in the annotator list', user)
        return abort(404)

@app.route("/<user>/save_changes", methods=["POST"])
def save_changes(user):
    annotations = request.get_json()
    f = annotations['filename'].split('/')[-1]
    f_without_ext = f.split('.')[0]
    rkey = "{}-{}.json".format(user, f_without_ext)
    redis_db.set(rkey, json.dumps({annotations['filename'] : annotations}))
    return "saved changes.", 200

@app.route("/images/<user>/<img_file>")
def get_image(img_file):
    return send_file(request.path)

@app.route("/<user>/load")
def load(user):
    annotations = {}
    for rkey in redis_db.keys():
        if rkey.decode("utf8").split("-")[0] == user:
            raw_json = redis_db.get(rkey).decode("utf8")
            data = json.loads(raw_json)
            for key, value in data.items():
                image_name = key.split("/")[-1]
                annotations["{}/static/images/{}/{}".format(APP_URL, user, image_name)] = value
    return jsonify(annotations)

set_logger()
create_folder_structure()
# app.run(host=app.config['HOST'],port=int(app.config['PORT']))
serve(app, host=app.config['HOST'],port=int(app.config['PORT']))
