function _via_load_submodules() {
  // _via_basic_demo_load_img();
  //_via_basic_demo_draw_default_regions();

  // _via_basic_demo_define_attributes();
  // _via_loader();
  toggle_attributes_editor();
  update_attributes_update_panel();

  annotation_editor_show();
}

function _via_loader() {
  // add files
  var i, n;
  var file_count = 0;
  n = _via_basic_demo_img.length;
  for ( i = 0; i < n; ++i ) {

    file_count += 1;
  }

  _via_show_img(0);
  update_img_fn_list();
}

function _via_define_attributes() {
  var attributes_json = '{"region":{"type":{"type":"dropdown","description":"Category of object","options":{"t":"title","h":"header","text":"text box","figure":"figure", "unknown":"Unknown"},"default_options":{"unknown":true}}}}'
  project_import_attributes_from_json(attributes_json);
}


// save to server setup
var annotator = '{{annotator}}';
var app_url = '{{flask_app_url}}';


function init_payload() {
    for (var i=0; i<img_url_list.length; ++i) {
    	var url = img_url_list[i];
    	var filename = url.substring(url.lastIndexOf('/')+1);
    	var img = new file_metadata(url, 0);
    	img.base64_img_data = url;


    	var img_id = _via_get_image_id(url);
    	_via_image_filename_list.push(filename);
    	_via_img_metadata[img_id] = img;
    	_via_image_id_list.push(img_id);
    	_via_img_count += 1;
    	_via_reload_img_table = true;
    }
    //_via_image_index = get_random_int(0, img_url_list.length);

    _via_image_index = 0;
    _via_show_img(_via_image_index);
    _via_define_attributes();
    update_img_fn_list();
}
