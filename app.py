import os
import sys
import time
from datetime import datetime
import json
import logging
import redis
import base64
from logging.handlers import RotatingFileHandler
from flask import Flask, abort, flash, redirect, render_template, request, url_for, jsonify, send_file

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
        attributes_dir = os.path.join(app.static_folder, 'attributes/' + annotator)
        if not os.path.exists(image_dir):
            app.logger.warn("creating image dir %s" % image_dir)
            os.makedirs(image_dir)
        if not os.path.exists(attributes_dir):
            app.logger.warn("creating attributes dir %s" % attributes_dir)
            os.makedirs(attributes_dir)

def get_image_url_list(annotator):
    '''
    Return a list of URIs for the images.
    '''
    image_path = os.path.join(app.static_folder, 'images/' + annotator)
    if os.path.exists(image_path):
        files = os.listdir(image_path)
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

def get_transcribed_image_urls(image_url_list, user):
    '''
    Return subset of images which have text in them
    '''
    transcribed_images = []
    for image in image_url_list:
        data = get_annotation(image, user)
        for key, value in data.items():
            for box, text in value["regions"].items():
                if text['region_attributes'].get('Text', None) is not None:
                    transcribed_images.append(image)
                    break
    return transcribed_images

def get_annotation_attributes(annotator):
    '''
    Return a list of attributes to be annotated by the user.
    '''
    annot_attribute_file = os.path.join(app.static_folder, 'attributes/' + annotator + '/list_of_attributes.txt')
    if not os.path.exists(annot_attribute_file):
        return []
    else:
        with open(annot_attribute_file, 'r') as fh:
            return [line.strip() for line in fh.readlines() if len(line.strip())]

def get_files_data():
    '''
    :return: list of (filename, data) tuples
    '''
    #get_image_url_list annotator
    filename = "10619-0.jpg"
    with open("static/images/1/10619-0.jpg", "rb") as image_file:
        filedata = base64.b64encode(image_file.read())

    return [str(filename), str(filedata)]

@app.route("/<user>", defaults={"subset": None})
@app.route("/<user>/<int:subset>")
@app.route("/<user>/unboxed/<int:subset>")
@app.route("/<user>/boxed/<int:subset>")
@app.route("/<user>/transcribed/<int:subset>")
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
        if 'transcribed' in request.path:
            image_url_list = get_transcribed_image_urls(image_url_list, user)
            
        attributes_list = get_annotation_attributes(user)
        if not image_url_list:
            app.logger.error('Image list not obtained for user:%s', user)
        if not attributes_list:
            app.logger.error('Annotation attributes list not obtained for user:%s', user)
        return render_template('via.html', annotator=user, image_list=image_url_list,
                               flask_app_url=APP_URL, attributes_list=attributes_list, test=get_files_data())
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
