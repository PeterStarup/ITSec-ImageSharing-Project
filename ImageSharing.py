import os
import sqlite3
from flask import Flask, request, session, g, redirect, url_for, \
    abort, render_template, flash
import base64
from itsdangerous import TimedJSONWebSignatureSerializer as Serializer
from flask_httpauth import HTTPTokenAuth

# configuration
# DATABASE = './tmp/database.db'
DATABASE = os.path.dirname(os.path.abspath(__file__)) + '/tmp/database.db'
DEBUG = False
SECRET_KEY = 'development key'

UPLOAD_FOLDER = './upload'
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif'}

# create our little application :)
app = Flask(__name__)
app.config.from_object(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.jinja_env.autoescape = True
app.config['SECRET_KEY'] = 'top secret!'
token_serializer = Serializer(app.config['SECRET_KEY'], expires_in=3600)

auth = HTTPTokenAuth('Bearer')

users = ['john', 'susan']
for user in users:
    token = token_serializer.dumps({'username': user}).decode('utf-8')
    print('*** token for {}: {}\n'.format(user, token))


@auth.verify_token
def verify_token(token):
    try:
        data = token_serializer.loads(token)
    except:  # noqa: E722
        return False
    if 'username' in data:
        return data['username']


@app.before_request
def before_request():
    g.db = connect_db()


@app.teardown_request
def teardown_request(exception):
    db = getattr(g, 'db', None)
    if db is not None:
        db.close()


def connect_db():
    return sqlite3.connect(app.config['DATABASE'])


def get_env_dir():
    return os.path.dirname(os.path.abspath(__file__))


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/create', methods=['GET', 'POST'])
def create():
    error = None
    if request.method == 'POST':
        if request.form['username'] == "":
            error = 'Username needed'
        elif request.form['password'] == "" or request.form['repassword'] == "":
            error = 'Password needed'
        elif request.form['password'] != request.form['repassword']:
            error = 'Password is not the same as the retyped'
        else:
            username = str(request.form['username'])
            query = "select username from user where username = " + "'" + str(username) + "'"
            cur = g.db.execute(query)
            u = [dict(password=row[0]) for row in cur.fetchall()]
            if len(u) == 0:
                g.db.execute('insert into user (username, password, token) values (?, ?, ?)',
                             [request.form['username'], request.form['password'], ''])
                g.db.commit()

                flash('Successfully created - You can now login')
                return redirect(url_for('login'))
            else:
                error = 'Username is taken'
    return render_template('create.html', error=error)


@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        cur = g.db.execute("select password from user where username = '{}'".format(username))
        pass_db = [dict(password=row[0]) for row in cur.fetchall()]
        if pass_db[0].get('password') is None:
            error = 'Invalid username or password'
            return render_template('login.html', error=error)
        p = pass_db[0].get('password')

        if p == password:
            cur = g.db.execute("select id from user where username = '{}'".format(username))
            rows = [dict(id=row[0]) for row in cur.fetchall()]
            user_id = rows[0].get('id')

            session['logged_in'] = True
            session['user_id'] = user_id
            flash('You were logged in')
            return redirect(url_for('profile'))
        else:
            error = 'Invalid username or password'
    return render_template('login.html', error=error)


@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    flash('You were logged out')
    return redirect(url_for('index'))


@app.route('/add', methods=['POST'])
@auth.login_required()
def add_entry():
    if not session.get('logged_in'):
        abort(401)
    g.db.execute(
        "insert into entries (title, text) values ('{}', '{}')".format(request.form['title'], request.form['text']))
    g.db.commit()
    flash('New entry was successfully posted')
    return redirect(url_for('show_entries'))


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/upload', methods=['GET', 'POST'])
@auth.login_required()
def upload():
    if request.method == 'POST':
        file = request.files['file']
        if file and allowed_file(file.filename):
            filename = file.filename

            user_id = get_userid()

            g.db.execute('insert into images (image, user_id, filename) values (?, ?, ?)',
                         (base64.b64encode(file.read()), user_id, filename))
            g.db.commit()

            flash('uploaded image: %s' % filename)
            return redirect(url_for('profile'))
        else:
            flash('filetype not allowed')

    return render_template('upload.html')


def blob_to_image(filename, ablob):
    folder = get_env_dir() + '/static/img/'
    with open(folder + filename, 'wb') as output_file:
        output_file.write(base64.b64decode(ablob))
    return filename


@app.route('/profile', methods=['GET'])
@auth.login_required()
def profile():
    id = session.get('user_id')

    cur = g.db.execute("select id, image, filename from images where user_id = '{}'".format(id))
    images = [dict(image_id=row[0], image=blob_to_image(row[2], row[1])) for row in cur.fetchall()]

    cur = g.db.execute(
        "select images.id, images.image, images.filename from images inner join share on images.id = share.image_id where share.to_id = '{}'".format(
            id))
    shared_images = [dict(image_id=row[0], image=blob_to_image(row[2], row[1])) for row in cur.fetchall()]

    return render_template('profile.html', images=images, shared_images=shared_images)


@app.route('/showimage/<id>/', methods=['GET'])
@auth.login_required()
def show_image(id):
    user_id = get_userid()
    if has_permission(id, user_id):
        cur = g.db.execute("select image, filename, user_id from images where id = {}".format(id))
        img = [dict(filename=row[1], image=blob_to_image(row[1], row[0]), user_id=row[2]) for row in cur.fetchall()]

        cur = g.db.execute('select id, username from user')
        usr = [dict(id=row[0], username=row[1]) for row in cur.fetchall()]

        cur = g.db.execute(
            "select share.id, user.username from share inner join user on user.id == share.to_id where from_id = {} and share.image_id = {}".format(
                user_id, id))
        share = [dict(id=row[0], username=row[1]) for row in cur.fetchall()]

        cur = g.db.execute(
            "select user.username, comments.comment from user inner join comments on user.id == comments.user_id where comments.image_id = {}".format(
                id))
        comments = [dict(username=row[0], comment=row[1]) for row in cur.fetchall()]

        return render_template('image.html', imageid=id, image=img, usernames=usr, shares=share, comments=comments,
                               owner=img[0].get('user_id') == user_id)
    else:
        return redirect(url_for('no_way'))


def has_permission(img_id, user_id):
    cur = g.db.execute("select user_id from images where id = {}".format(img_id))
    img_user_id = [dict(user_id=row[0]) for row in cur.fetchall()]

    if user_id == img_user_id[0].get('user_id'):
        return True

    cur = g.db.execute(
        "select id from share where image_id = {} and to_id = {}".format(img_id, user_id))
    share = [dict(id=row[0]) for row in cur.fetchall()]

    if len(share) > 0:
        return True
    return False


@app.route('/shareimage', methods=['POST'])
@auth.login_required()
def share_image():
    if request.method == 'POST':
        image_id = request.form['imageid']
        to_userid = request.form['userid']

        if has_permission(image_id, get_userid()):
            g.db.execute("insert into share (image_id, to_id, from_id) values ({}, {}, {})".format(image_id, to_userid,
                                                                                                   get_userid()))
            g.db.commit()
            flash('Image shared')
            return redirect(url_for('show_image', id=image_id))


@app.route('/unshare', methods=['POST'])
@auth.login_required()
def unshare():
    if request.method == 'POST':
        shared_id = request.form['shareduser']
        image_id = request.form['imageid']

        g.db.execute("delete from share where id = {}".format(shared_id))
        g.db.commit()
        flash('Image unshared')
        return redirect(url_for('show_image', id=image_id))
    else:
        return redirect(url_for('no_way'))


@app.route('/no_way', methods=['GET'])
@auth.login_required()
def no_way():
    return render_template('no_way.html')


@app.route('/add_comment', methods=['POST'])
@auth.login_required()
def add_comment():
    if request.method == 'POST':
        # TODO: needs to check for access
        image_id = request.form['imageid']
        userid = get_userid()
        comment = request.form['text']

        g.db.execute(
            "insert into comments (user_id, image_id, comment) values ({}, {}, '{}')".format(userid, image_id, comment))
        g.db.commit()
        flash('Added comment')

        return redirect(url_for('show_image', id=image_id))


def get_userid():
    return session.get('user_id')


@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80)
