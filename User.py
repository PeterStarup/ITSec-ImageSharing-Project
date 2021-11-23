from ImageSharing import db
from werkzeug.security import generate_password_hash, check_password_hash
from ImageSharing import token_serializer


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(80), unique=True, nullable=False) # user name
    hash_password = db.Column(db.String(120), nullable=False)

    # Clear text password (read only)
    @property
    def password(self):
        raise AttributeError('unreadable ')

    # Write the password, calculate the hash value at the same time, and save it in the model
    @password.setter
    def password(self,value):
        self.hash_password = generate_password_hash(value)

    # Check if the password is correct
    def check_password(self, password):
        return check_password_hash(self.hash_password,password)

    # Generate token
    @staticmethod
    def create_token(user_id):
        """
        //Generate token
        :param user_id: user id
        :return:
        """

        # The first parameter is the internal private key, which is written in the configuration information. If it is just a test, it can be written dead
        # The second parameter is the validity period (seconds)
        s = token_serializer
        # Receive user id conversion and coding
        token = s.dumps({"id": user_id}).decode('ascii')
        return token