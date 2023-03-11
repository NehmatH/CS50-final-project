import os
import webbrowser
import urllib.request
import json
import urllib
import pprint

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session, Response
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime

from helpers import login_required, lbp

app = Flask(__name__)

app.config["TEMPLATES_AUTO_RELOAD"] = True

@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

db = SQL("sqlite:///event.db")

@app.route("/")
def index():
    return render_template("index.html", index=".")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":

        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")
        hashed_password = generate_password_hash(password)

        rows = db.execute("SELECT id FROM users WHERE username = :username", username=username)
        if len(rows) == 1:
            return render_template("register.html", message="Username already exists.", index=".")


        if password != confirmation:
            return render_template("register.html", message="Passwords don't match.", index=".")


        now = datetime.now()
        time = now.strftime("%Y-%m-%d %H:%M:%S")
        year = now.strftime("%Y")
        days = now.strftime("%d/%m/%Y")

        db.execute("INSERT INTO users (username, hash, time, year, days) VALUES (?, ?, ?, ?, ?)", username, hashed_password, time, year, days)

        return redirect("/login")

    else:

        return render_template("register.html", index=".")

@app.route("/login", methods=["GET", "POST"])
def login():

    session.clear()

    if request.method == "POST":

        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        username = request.form.get("username")

        if len(rows) != 1:
            return render_template("login.html", message="Username does not exist.", index=".")

        if not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return render_template("login.html", message="Invalid password.", index=".")

        session["user_id"] = rows[0]["id"]

        return redirect("/events")

    else:
        return render_template("login.html", index=".")

@app.route("/logout")
def logout():

    session.clear()

    return redirect("/")

@app.route("/password", methods=["GET", "POST"])
@login_required
def changepassword():

    if request.method == "POST":

        currentpass = request.form.get("currentpassword")
        newpass = request.form.get("newpassword")

        oldpass = db.execute("SELECT hash FROM users WHERE id = ?", session['user_id'])

        if not check_password_hash(oldpass[0]["hash"], currentpass):
            return render_template("password.html", message="Invalid current password.")

        if check_password_hash(oldpass[0]["hash"], newpass) == True:
            return render_template("password.html", message="New password cannot be current password.")

        db.execute("UPDATE users SET hash = :hash WHERE id = :id", hash=generate_password_hash(newpass), id=session['user_id'])

        return redirect("/login")

    else:
        rows = db.execute("SELECT username, year FROM users WHERE id = ?", session['user_id'])

        username = rows[0]["username"]

        return render_template("password.html", username=username, home=".")


@app.route("/profile")
@login_required
def profile():
        rows = db.execute("SELECT username, year, days FROM users WHERE id = ?", session['user_id'])

        username = rows[0]["username"]
        year = rows[0]["year"]
        days = rows[0]["days"]

        return render_template("profile.html", username=username, days=days, year=year, home=".")

@app.route("/delete")
@login_required
def delete():
        rows = db.execute("SELECT username FROM users WHERE id = ?", session['user_id'])
        username = rows[0]["username"]

        parts = db.execute("SELECT participants FROM newevent WHERE participants LIKE ?", '%' + username + '%')
        for part in parts:
            if part["participants"].endswith(username):
                oldpar = part["participants"]
                part["participants"] = part["participants"].replace(" " + username, "")
                db.execute("UPDATE newevent set participants = ? WHERE participants = ?", part["participants"], oldpar)
            else:
                oldpar = part["participants"]
                part["participants"] = part["participants"].replace(username + " ", "")
                db.execute("UPDATE newevent set participants = ? WHERE participants = ?", part["participants"], oldpar)

        db.execute("DELETE FROM users WHERE id = :id", id=session['user_id'])
        db.execute("DELETE FROM accepted WHERE accept = ? or username = ?", username, username)
        db.execute("DELETE FROM friends WHERE request = ? or answer = ?", username, username)
        db.execute("DELETE FROM newevent WHERE username = ?", username)

        return redirect("/logout")

@app.route("/users", methods=["GET", "POST"])
@login_required
def users():
    rows = db.execute("SELECT username FROM users WHERE id = ?", session['user_id'])
    username = rows[0]["username"]

    friends = []
    users = db.execute("SELECT username FROM users ORDER BY username COLLATE NOCASE ASC")
    accepts = db.execute("SELECT accept FROM accepted WHERE id=?", session['user_id'])
    userss = db.execute("SELECT username FROM accepted WHERE accept = ?", username)

    for accept in accepts:
        friends.append(accept['accept'])

    for users1 in userss:
        friends.append(users1['username'])

    people = []

    for user in users:
        people.append(user)

    for person in people:
        for friend in friends:
            if person['username'] == friend:
                people.remove(person)
        if person['username'] == username:
            people.remove(person)

    for person in people:
        for friend in friends:
            if person['username'] == friend:
                people.remove(person)
        if person['username'] == username:
            people.remove(person)

    if request.method == "GET":
        return render_template("users.html", users=users, username=username, people=people, home=".")
    else:
        add = request.form.get("friend_id")
        db.execute("INSERT INTO friends (id, request, answer) VALUES (?, ?, ?)", session['user_id'], username, add)
        return render_template("users.html", message="Friend Request Sent!", users=users, username=username, people=people, home=".")

@app.route("/friends", methods=["GET", "POST"])
@login_required
def friends():
    rows = db.execute("SELECT username FROM users WHERE id = ?", session['user_id'])
    username = rows[0]["username"]
    friends = db.execute("SELECT request FROM friends WHERE answer = ? GROUP BY request", username)

    if request.method == "GET":
        accepts = db.execute("SELECT accept FROM accepted WHERE id=?", session['user_id'])
        userss = db.execute("SELECT username FROM accepted WHERE accept = ?", username)
        if not friends:
            if not accepts and not userss:
                return render_template("friends.html", username=username, friends=friends, accepts=accepts, users=userss, message1="Looks like you have no friend requests at the moment!", message2="Looks like you have no friends at the moment!", home=".")
            return render_template("friends.html", username=username, friends=friends, accepts=accepts, users=userss, message1="Looks like you have no friend requests at the moment!", home=".")
        elif not accepts and not userss:
            return render_template("friends.html", username=username, friends=friends, accepts=accepts, users=userss, message2="Looks like you have no friends at the moment!", home=".")
        return render_template("friends.html", username=username, friends=friends, accepts=accepts, users=userss, home=".")
    else:
        user = request.form.get("userr")
        db.execute("DELETE FROM friends WHERE request = ? AND answer = ?", user, username)
        friends = db.execute("SELECT request FROM friends WHERE answer = ? GROUP BY request", username)

        if 'accept' in request.form:
            db.execute("INSERT INTO accepted (id, username, accept) VALUES (?, ?, ?)", session['user_id'], username ,user)
            accepts = db.execute("SELECT accept FROM accepted WHERE id=?", session['user_id'])
            userss = db.execute("SELECT username FROM accepted WHERE accept = ?", username)
            if not friends:
                if not accepts and not userss:
                    return render_template("friends.html", username=username, friends=friends, accepts=accepts, users=userss, message1="Looks like you have no friend requests at the moment!", message2="Looks like you have no friends at the moment!", home=".")
                return render_template("friends.html", username=username, friends=friends, accepts=accepts, users=userss, message1="Looks like you have no friend requests at the moment!", home=".")
            elif not accepts and not userss:
                return render_template("friends.html", username=username, friends=friends, accepts=accepts, users=userss, message2="Looks like you have no friends at the moment!", home=".")
            return render_template("friends.html", username=username, friends=friends, accepts=accepts, users=userss, home=".")
        else:
            accepts = db.execute("SELECT accept FROM accepted WHERE id=?", session['user_id'])
            userss = db.execute("SELECT username FROM accepted WHERE accept = ?", username)
            if not friends:
                if not accepts and not userss:
                    return render_template("friends.html", username=username, friends=friends, accepts=accepts, users=userss, message1="Looks like you have no friend requests at the moment!", message2="Looks like you have no friends at the moment!", home=".")
                return render_template("friends.html", username=username, friends=friends, accepts=accepts, users=userss, message1="Looks like you have no friend requests at the moment!", home=".")
            elif not accepts and not userss:
                return render_template("friends.html", username=username, friends=friends, accepts=accepts, users=userss, message2="Looks like you have no friends at the moment!", home=".")
            return render_template("friends.html", username=username, friends=friends, accepts=accepts, users=userss, home=".")


@app.route("/about")
def about():
    return render_template("about.html", index=".")

@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "GET":
        return render_template("contact.html", index=".")
    else:
        name = request.form.get("name")
        email = request.form.get("email")
        message = request.form.get("message")

        now = datetime.now()
        time = now.strftime("%Y-%m-%d %H:%M:%S")

        db.execute("INSERT INTO contact (name, email, message, time) VALUES (?, ?, ?, ?)", name, email, message, time)
        return render_template("contact.html", index=".", message="Message Sent!")


@app.route("/remove", methods=["POST"])
@login_required
def remove():
    if request.method == "POST":
        rows = db.execute("SELECT username FROM users WHERE id = ?", session['user_id'])
        username = rows[0]["username"]
        friends = []
        accepts = db.execute("SELECT accept FROM accepted WHERE id=?", session['user_id'])
        userss = db.execute("SELECT username FROM accepted WHERE accept = ?", username)

        for accept in accepts:
            friends.append(accept['accept'])

        for users1 in userss:
            friends.append(users1['username'])

        dele = request.form.get("dele")
        db.execute("DELETE FROM accepted WHERE (accept = ? AND username = ?) OR (accept = ? AND username = ?)", dele, username, username, dele)

        return redirect("/friends")
    else:
        return redirect("")


@app.route("/new", methods=["GET", "POST"])
@login_required
def newevent():
    rows = db.execute("SELECT username FROM users WHERE id = ?", session['user_id'])
    username = rows[0]["username"]
    accepts = db.execute("SELECT accept FROM accepted WHERE id=?", session['user_id'])
    userss = db.execute("SELECT username FROM accepted WHERE accept = ?", username)

    friends = []
    for accept in accepts:
        friends.append(accept['accept'])

    for users1 in userss:
        friends.append(users1['username'])

    if request.method == "GET":
        return render_template("event.html", username=username, users=userss, accepts=accepts, home=".")
    else:
        title = request.form.get("title1")
        location = request.form.get("location")
        date1 = request.form.get("option1")
        date2 = request.form.get("option2")
        date3 = request.form.get("option3")
        start = request.form.get("start")
        end = request.form.get("end")
        notes = request.form.get("notes")
        parts = request.form.getlist('partss')
        parts.append(username)
        parts = ', '.join(parts)

        now = datetime.now()
        time = now.strftime("%Y-%m-%d %H:%M:%S")
        days = now.strftime("%d/%m/%Y")

        if start >= end:
            return render_template("event.html", username=username, users=userss, accepts=accepts, message1="The start date must be before the end date.", home=".")

        db.execute("INSERT INTO newevent (id, username, title, location, date1, start, end, time, days, notes, participants) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", session['user_id'], username, title, location, date1, start, end, time, days, notes, parts)

        return render_template("event.html", username=username, users=userss, accepts=accepts, message="Event Created!", home=".")


@app.route("/events", methods=["GET", "POST"])
@login_required
def events():

    rows = db.execute("SELECT username FROM users WHERE id = ?", session['user_id'])
    username = rows[0]["username"]
    accepts = db.execute("SELECT accept FROM accepted WHERE id=?", session['user_id'])
    userss = db.execute("SELECT username FROM accepted WHERE accept = ?", username)
    friends = []
    for accept in accepts:
        friends.append(accept['accept'])

    for users1 in userss:
        friends.append(users1['username'])

    userevents = []
    parts = db.execute("SELECT event_id, participants FROM newevent ORDER BY date1 ASC")
    for part in parts:
        if username in part["participants"]:
            userevents.append(part["event_id"])

    allevents = []
    for event in userevents:
        events = db.execute("SELECT event_id, username, title, location, date1, start, end, notes, participants, days FROM newevent WHERE event_id = ?", event)
        allevents.append(events)

    eachevent = []
    for first in allevents:
        for firstevent in first:
            eachevent.append(firstevent)

    if request.method == "GET":
        return render_template("events.html", username=username, eachevent=eachevent, friends=friends, home=".")
    else:
        if 'leave' in request.form:
            eventid = request.form.get("leave")
            parts = db.execute("SELECT participants FROM newevent WHERE event_id = ?", eventid)
            participants = parts[0]["participants"]
            if participants.endswith(username):
                participants = participants.replace(", " + username, '')
            else:
                participants = participants.replace(username + ", ", '')

            db.execute("UPDATE newevent SET participants = ? WHERE event_id = ?", participants, eventid)
            return redirect("/events")

        if 'deleteevent' in request.form:
            eventid = request.form.get("deleteevent")
            db.execute("DELETE FROM newevent WHERE event_id = ?", eventid)
            return redirect("/events")

        if 'remove' in request.form:
            eventid = request.form.get("remove")
            toremove = request.form.getlist("removeone")
            parts = db.execute("SELECT participants FROM newevent WHERE event_id = ?", eventid)
            participants = parts[0]["participants"]

            for part1 in toremove:
                if participants.endswith(part1):
                    participants = participants.replace(", " + part1, '')
                else:
                    participants = participants.replace(part1 + ", ", '')

            db.execute("UPDATE newevent SET participants = ? WHERE event_id = ?", participants, eventid)

            return redirect("/events")

        if 'add' in request.form:
            eventid = request.form.get("add")
            toadd = request.form.getlist("addone")
            parts = db.execute("SELECT participants FROM newevent WHERE event_id = ?", eventid)
            participants = parts[0]["participants"]

            for part1 in toadd:
                participants += ", " + part1

            db.execute("UPDATE newevent SET participants = ? WHERE event_id = ?", participants, eventid)

            return redirect("/events")


