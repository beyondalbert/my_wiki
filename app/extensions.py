"""Flask extensions singletons."""
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect


db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()


login_manager.login_view = "auth.login"
login_manager.login_message = "请先登录后再访问该页面"
login_manager.login_message_category = "warning"
