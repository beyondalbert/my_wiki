"""Auth blueprint: register / login / logout / captcha."""
from flask import Blueprint, flash, redirect, render_template, request, url_for, Response
from flask_login import login_user, logout_user, login_required, current_user

from ..services import auth_service, captcha_service

bp = Blueprint("auth", __name__)


@bp.route("/captcha")
def captcha():
    png = captcha_service.issue_captcha()
    return Response(png, mimetype="image/png", headers={
        "Cache-Control": "no-store, no-cache, must-revalidate",
        "Pragma": "no-cache",
    })


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("user.dashboard"))

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        email = (request.form.get("email") or "").strip()
        password = request.form.get("password") or ""
        password2 = request.form.get("password2") or ""
        captcha_input = request.form.get("captcha") or ""

        if not captcha_service.verify_captcha(captcha_input):
            flash("验证码错误或已过期，请重试", "error")
            return render_template("auth/register.html",
                                   form={"username": username, "email": email})
        try:
            auth_service.validate_register(username, email, password, password2)
        except auth_service.AuthError as e:
            flash(str(e), "error")
            return render_template("auth/register.html",
                                   form={"username": username, "email": email})

        user = auth_service.register(username, email, password)
        login_user(user)
        auth_service.mark_login(user)
        flash("注册成功，欢迎加入麦威知识库", "success")
        return redirect(url_for("user.dashboard"))

    return render_template("auth/register.html", form={})


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("user.dashboard"))

    if request.method == "POST":
        login_value = (request.form.get("login") or "").strip()
        password = request.form.get("password") or ""
        captcha_input = request.form.get("captcha") or ""
        remember = bool(request.form.get("remember"))

        if not captcha_service.verify_captcha(captcha_input):
            flash("验证码错误或已过期，请重试", "error")
            return render_template("auth/login.html", form={"login": login_value})

        user = auth_service.authenticate(login_value, password)
        if not user:
            flash("用户名或密码错误", "error")
            return render_template("auth/login.html", form={"login": login_value})

        login_user(user, remember=remember)
        auth_service.mark_login(user)
        next_url = request.args.get("next") or url_for("user.dashboard")
        return redirect(next_url)

    return render_template("auth/login.html", form={})


@bp.route("/logout", methods=["POST", "GET"])
@login_required
def logout():
    logout_user()
    flash("您已退出登录", "info")
    return redirect(url_for("auth.login"))
