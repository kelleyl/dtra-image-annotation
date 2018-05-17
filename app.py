import os
import sys
import time
from datetime import datetime
import json
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, abort, flash, redirect, render_template, request, url_for, jsonify, send_file

from waitress import serve


app = Flask(__name__)
app.config.from_pyfile('config_file.cfg')

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
    waitress_logger = logging.getLogger('waitress')
    waitress_logger.setLevel(logging.INFO)
    waitress_handler = RotatingFileHandler('waitress_server.log', maxBytes=9e9, backupCount=1)
    waitress_logger.addHandler(waitress_handler)

def create_folder_structure():
    '''
    Create folder structure in static folder for annotation.
    '''
    for annotator in ANNOTATORS:
        annotation_dir = os.path.join(app.static_folder, 'annotations/' + annotator)
        image_dir = os.path.join(app.static_folder, 'images/' + annotator)
        attributes_dir = os.path.join(app.static_folder, 'attributes/' + annotator)
        if not os.path.exists(annotation_dir):
            app.logger.warn("creating annotation dir %s" % annotation_dir)
            os.makedirs(annotation_dir)
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

def get_boxed_image_urls(image_url_list, user):
    '''
    Return subset of images for which boxes have been drawn.
    '''
    annotation_dir = os.path.join(app.static_folder, 'annotations/' + user)
    if not os.path.exists(annotation_dir):
        app.logger.error("[get_boxed_image_urls] Annotation dir:%s doesnot exist.")
        return []

    boxed_images = []
    for image in image_url_list:
        annotation = image.split("/")[-1].split(".")[0] + ".json"
        annotation_path = os.path.join(annotation_dir, annotation)
        if os.path.exists(annotation_path):
            try:
                with open(annotation_path, "r") as fh:
                    annot_data = json.load(fh)
                    for key, value in annot_data.items():
                        if len(value["regions"]):
                            boxed_images.append(image)
            except:
                app.logger.error('get_boxed_image_urls path:%s failed error:%s', annotation_path, sys.exc_info()[0])
    return boxed_images

def get_transcribed_image_urls(image_url_list, user):
    '''
    Return subset of images which have text in them
    '''
    annotation_dir = os.path.join(app.static_folder, 'annotations/' + user)
    if not os.path.exists(annotation_dir):
        app.logger.error("[get_transcribed_image_urls] Annotation dir:%s doesnot exist.")
        return []

    transcribed_images = []
    for image in image_url_list:
        annotation = image.split("/")[-1].split(".")[0] + ".json"
        annotation_path = os.path.join(annotation_dir, annotation)
        if os.path.exists(annotation_path):
            try:
                with open(annotation_path, "r") as fh:
                    annot_data = json.load(fh)
                    for key, value in annot_data.items():
                        for box, text in value["regions"].items():
                            if text['region_attributes'].get('Text', None) is not None:
                                transcribed_images.append(image)
                                break
            except:
                app.logger.error('get_transcribed_image_urls path:%s failed error:%s', annotation_path, sys.exc_info()[0])
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
                               flask_app_url=APP_URL, attributes_list=attributes_list)
    else:
        app.logger.error('User:%s not in the annotator list', user)
        return abort(404)
        
@app.route("/<user>/save_changes", methods=["POST"])
def save_changes(user):
    annotation_dir = os.path.join(app.static_folder, 'annotations/' + user)
    annotations = request.get_json()
    f = annotations['filename'].split('/')[-1]
    file_ext = f.split('.')[-1]
    annotation_file_name = f.replace(file_ext, 'json')
    annotation_file_path = os.path.join(annotation_dir, annotation_file_name)
    try:
        with open(annotation_file_path, 'w') as handle:
            json.dump({annotations['filename']:annotations}, handle)
    except:
        app.logger.error('save changes(file_path:%s) request received for user:%s failed', annotation_file_path, user)
        return "Save changes failed", 500
    return "Saved changes.", 200

@app.route("/<user>/save", methods=['POST'])
def save(user):
    annotation_dir = os.path.join(app.static_folder, 'annotations/' + user)
    annotations = request.get_json()
    annotation_file_name = user + '_annotations_' + time.strftime("%Y_%m_%d_%H:%M:%S", time.localtime()) + '.json'
    annotation_file_path = os.path.join(annotation_dir, annotation_file_name)
    try:
        with open(annotation_file_path, 'w') as handle:
            json.dump(annotations, handle)
    except:
        app.logger.error('save (file_path:%s) request received for user:%s failed error:%s', annotation_file_path, user, sys.exc_info()[0])
        return 'Annotation save failed.', 500
    return "Annotations saved.", 200

@app.route("/images/<user>/<img_file>")
def get_image(img_file):
    return send_file(request.path)

@app.route("/<user>/load")
def load(user):
    annotation_dir = os.path.join(app.static_folder, 'annotations/' + user)
    if not os.path.exists(annotation_dir):
        return 'load failed. Annotation dir not present for the user:%s' % user, 501
    files = os.listdir(annotation_dir)
    annotations = {}
    for file in files:
        f_path = os.path.join(annotation_dir, file)
        try:
            with open(f_path, 'r') as fh:
                f_annotations = json.load(fh)
            for key, value in f_annotations.items():
                image_name = key.split("/")[-1]
                annotations["{}/static/images/{}/{}".format(APP_URL, user, image_name)] = value
        except:
            app.logger.error('load annotations(file_path:%s) for user:%s failed error:%s', f_path, user, sys.exc_info()[0])
    return jsonify(annotations)

@app.route('/annotations', defaults={'req_path': ''})
@app.route('/annotations/<path:req_path>')
def dir_listing(req_path):
    base_dir = os.path.join(app.static_folder, 'annotations')
    # Joining the base and the requested path
    abs_path = os.path.join(base_dir, req_path)

    # Return 404 if path doesn't exist
    if not os.path.exists(abs_path):
        app.logger.error('annotation path(%s) doesn\'t exist', abs_path)
        return abort(404)

    # Check if path is a file and serve
    if os.path.isfile(abs_path):
        return send_file(abs_path)

    # Show directory contents
    files = os.listdir(abs_path)
    if req_path is '':
        req_path = 'annotations'
    files = [os.path.join(req_path, f) for f in files]
    return render_template('files.html', files=files)


set_logger()
create_folder_structure()
# app.run(host=app.config['HOST'],port=int(app.config['PORT']))
serve(app, host=app.config['HOST'],port=int(app.config['PORT']))
