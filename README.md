# image-annotation
A server based setup for VIA tool(http://www.robots.ox.ac.uk/~vgg/software/via/)

To run the app, set FLASK_APP environment variable as the path to app.py file.

To start annotation make the following changes:

1. Add the <username> in the list ANNOTATORS present in the app.py file. 
2. Create a folder static/images/<username> and populate the folder with images assigned to the user.

Command to run the app - 'flask run'
