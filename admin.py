from flask import request, jsonify, Response, json, redirect, abort, render_template, session
from hackhub import app, get_db
from member import Member, all_member, new_member, active_members
from status import Status, new_status
import settings
import datetime, time
from decorators import login_required, admin_required
from find_gaps import find_gaps
import ldap

@app.route('/hub/admin')
@login_required
@admin_required
def admin_home():
    return render_template('admin.html', members=[m for m in all_member() if m.is_active()])

@app.route('/hub/admin/payment', methods=['POST'])
def admin_payment():
    if 'username' in session:
        user = Member(session['username'])
        if not user.is_admin():
            abort(403)
        member = Member(request.form['username'])
        if 'month' in request.form.keys():
            try:
                month = int(request.form['month'])
                if not(1 <= month <= 12):
                    return render_template('message.html', title='Fail', message='That is an unacceptable month')
                year = int(request.form['year'])
                delta_yr = datetime.date.today().year - year
                if not(-1 <= delta_yr <= 1):
                    return render_template('message.html', title='Fail', message='That is an unacceptable year')
                member.add_payment(month, year, session['username'])
                return redirect('/hub/admin')
            except Exception as e:
                return render_template('message.html', title='Fail', message=str(e))
        else:
            member.add_payment(int(time.strftime("%m")), int(time.strftime("%Y")), session['username'])
        return redirect('/hub/admin')
    else:
        return redirect('/hub/login')

@app.route('/hub/admin/bank_payment', methods=['POST'])
def admin_bank_payment():
    if 'username' in session:
        user = Member(session['username'])
        if not user.is_admin():
            abort(403)
        member = Member(request.form['username'])
        member.add_bank_payment(int(time.strftime("%m")), int(time.strftime("%Y")), session['username'])
        return redirect('/hub/admin')
    else:
        return redirect('/hub/login')
    
    
@app.route('/hub/admin/profile', methods=['GET', 'POST'])
def admin_profile():
    if 'username' in session:
        user = Member(session['username'])
        if not user.is_admin():
            abort(403)        
        if request.method == 'GET':
            return render_template('admin_profile_edit.html', profile=Member(request.args['u']).get_profile())
        elif request.method == 'POST':
            updatable = ['realname', 'nickname', 'email', 'twitter', 'irc', 'github', 'address']
            update = {}
            for x in request.form:
                if x in updatable:
                    update[x] = None if request.form[x] == 'None' else request.form[x]
            m = Member(request.form['username'])
            m.update_profile(update)
            return redirect('/hub/admin')
    else:
        return redirect('/hub/login')

@app.route('/hub/admin/payment_hist')
def payment_hist():
    if 'username' in session:
        user = Member(session['username'])
        if not user.is_admin():
            abort(403)
        return render_template('admin_payment_hist.html', user=Member(request.args['u']))
    else:
        return redirect('/hub/login')

@app.route('/hub/admin/payment_dashboard')
def payment_dashboard():
    if 'username' in session:
        user = Member(session['username'])
        if not user.is_admin():
            abort(403)
        hists = {}
        for m in active_members():
            hists[m] = Member(m).payment_history()
        return render_template('admin_payment_dash.html', hists=hists)
    else:
        return redirect('/hub/login')

@app.route('/hub/admin/applications', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_applications():
    if request.method == 'GET':
        db = get_db()
        cur = db.cursor()
        cur.execute("""SELECT id, username, realname, nickname, email, address
            FROM application WHERE accepted=0 ORDER BY id DESC""")
        applications = cur.fetchall()
        cur.close()
        print applications
        return render_template('admin_applications.html', applications=applications)
    else:
        id = int(request.form['id'])
        db = get_db()
        cur = db.cursor()
        cur.execute("""SELECT username, realname, nickname, email, address
            FROM application WHERE id=? AND accepted=0""", (id,))
        row = cur.fetchone()
        if not row:
            cur.close()
            return redirect('/hub/admin/applications')

        details = dict(zip(row.keys(), row))
        username = details['username']
        details['key'] = 0
        details['adm'] = 0
        new_member(username, details)

        cur.execute('UPDATE application SET accepted=1 WHERE id=?', (id,))
        db.commit()
        cur.close()

        l = ldap.initialize(settings.LDAP_URI)
        l.simple_bind_s(settings.LDAP_BIND_DN, settings.LDAP_PASSWORD)
        l.modify_s(settings.LDAP_MEMBERS_GROUP_DN, [
            (ldap.MOD_ADD, "member", "uid="+username.encode("ascii", "ignore")+","+settings.LDAP_USERS_DN),
        ])

        return redirect('/hub/admin')

@app.route('/hub/admin/balance', methods=['GET', 'POST'])
def admin_balance():
    if 'username' in session:
        user = Member(session['username'])
        if not user.is_admin():
            abort(403)
        if request.method == 'GET':
            return render_template('admin_balance.html')
        elif request.method == 'POST':
            # update stuff

            pass
    else:
        return redirect('/hub/login')


@app.route('/hub/admin/behind')
def admin_behind():
    if 'username' in session:
        user = Member(session['username'])
        if not user.is_admin():
            abort(403)
        attrs = [int(time.strftime("%m")), int(time.strftime("%Y")),
                 int(time.strftime("%m")) - 1, int(time.strftime("%Y")),
                 int(time.strftime("%m")) - 2, int(time.strftime("%Y"))]
        #handle months being last year
        if attrs[2] <= 0:
            attrs[2] = 12 + attrs[2]
            attrs[3] = attrs[3] - 1
        if attrs[4] <= 0:
            attrs[4] = 12 + attrs[4]
            attrs[5] = attrs[5] -1
        attrs = tuple(attrs)
        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT username FROM member WHERE username NOT IN (SELECT username FROM payment WHERE (month == ? AND year == ?) OR (month == ? AND year == ?) OR (month == ? AND year == ?)) AND username NOT IN (SELECT user FROM dismembered)", attrs)
        users = cur.fetchall()
        behind = []
        for user in users:
            m = Member(user[0])
            try:
                year, month = m.get_payments()[0][0:2]
            except Exception:
                year, month = None, None
            behind.append((m.username, m.profile["realname"], m.profile["email"], year, month))
        return render_template('admin_behind.html', behind=behind)
    else:
        return redirect('/hub/login')

@app.route('/hub/admin/gaps')
def admin_gaps():
    if 'username' in session:
        user = Member(session['username'])
        if not user.is_admin():
            abort(403)
        gaps = find_gaps(6)
        return render_template('admin_gaps.html', gaps=gaps)
    else:
        return redirect('/hub/login')
            

@app.route('/hub/admin/payment_list')
def payment_list():
    if 'username' in session:
       user = Member(session['username'])
       if not user.is_admin():
           abort(403)
       db = get_db()
       cur = db.cursor()
       cur.execute("SELECT * FROM payment ORDER BY id;")
       payments = cur.fetchall()
       return render_template('admin_payments.html', payments=payments)
    else:
        return redirect('/hub/login')
