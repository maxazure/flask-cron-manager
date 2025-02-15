import os
import argparse
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, ValidationError
from wtforms.validators import DataRequired, Length, EqualTo
from werkzeug.security import generate_password_hash, check_password_hash
from crontab import CronTab

# 初始化Flask应用
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'  # 设置密钥，用于session加密
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///tasks.db'  # 使用SQLite数据库
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 初始化数据库和登录管理器
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = '请先登录后再访问此页面。'
login_manager.login_message_category = 'warning'

# 确保scripts目录存在
SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scripts')
os.makedirs(SCRIPTS_DIR, exist_ok=True)

# 用户模型
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# 任务模型
class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    cron_expression = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    script_content = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'cron_expression': self.cron_expression,
            'description': self.description,
            'script_content': self.script_content,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }

# 登录表单
class LoginForm(FlaskForm):
    username = StringField('用户名', validators=[DataRequired(), Length(min=3, max=80)])
    password = PasswordField('密码', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('确认密码')  # 仅用于首次设置

    def __init__(self, *args, **kwargs):
        super(LoginForm, self).__init__(*args, **kwargs)
        if kwargs.get('is_first_time'):
            self.confirm_password.validators = [
                DataRequired(),
                EqualTo('password', message='两次输入的密码不匹配')
            ]

# 修改密码表单
class ChangePasswordForm(FlaskForm):
    current_password = PasswordField('当前密码', validators=[DataRequired()])
    new_password = PasswordField('新密码', validators=[
        DataRequired(),
        Length(min=6, message='新密码长度至少为6个字符')
    ])
    confirm_new_password = PasswordField('确认新密码', validators=[
        DataRequired(),
        EqualTo('new_password', message='两次输入的新密码不匹配')
    ])

# Crontab管理类
class CrontabManager:
    def __init__(self):
        self.cron = CronTab(user=True)
    
    def add_or_update_job(self, task):
        # 移除旧的任务（如果存在）
        self.remove_job(task.id)
        
        # 创建新任务
        script_path = os.path.join(SCRIPTS_DIR, f'task_{task.id}.py')
        job = self.cron.new(command=f'python {script_path}')
        job.setall(task.cron_expression)
        job.set_comment(f'task_{task.id}')
        self.cron.write()
        
        # 保存脚本文件
        with open(script_path, 'w') as f:
            f.write(task.script_content)
    
    def remove_job(self, task_id):
        jobs = self.cron.find_comment(f'task_{task_id}')
        for job in jobs:
            self.cron.remove(job)
        self.cron.write()
        
        # 尝试删除脚本文件
        script_path = os.path.join(SCRIPTS_DIR, f'task_{task_id}.py')
        if os.path.exists(script_path):
            os.remove(script_path)

crontab_manager = CrontabManager()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# 登录路由
@app.route('/login', methods=['GET', 'POST'])
def login():
    # 检查是否是首次设置
    is_first_time = User.query.first() is None
    
    if current_user.is_authenticated and not is_first_time:
        return redirect(url_for('index'))
    
    form = LoginForm(is_first_time=is_first_time)
    
    if form.validate_on_submit():
        if is_first_time:
            # 创建管理员账号
            user = User(username=form.username.data)
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash('管理员账号创建成功！', 'success')
        else:
            # 常规登录
            user = User.query.filter_by(username=form.username.data).first()
            if user is None or not user.check_password(form.password.data):
                flash('用户名或密码错误', 'danger')
                return render_template('login.html', form=form, is_first_time=False)
            login_user(user)
            flash('登录成功！', 'success')
        
        next_page = request.args.get('next')
        return redirect(next_page or url_for('index'))
    
    return render_template('login.html', form=form, is_first_time=is_first_time)

# 退出登录路由
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('您已成功退出登录。', 'success')
    return redirect(url_for('login'))

# 修改密码路由
@app.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    form = ChangePasswordForm()
    if form.validate_on_submit():
        if not current_user.check_password(form.current_password.data):
            flash('当前密码错误', 'danger')
            return render_template('change_password.html', form=form)
        
        current_user.set_password(form.new_password.data)
        db.session.commit()
        flash('密码修改成功，请重新登录。', 'success')
        return redirect(url_for('logout'))
    
    return render_template('change_password.html', form=form)

# 路由：首页/任务列表
@app.route('/')
@login_required
def index():
    tasks = Task.query.all()
    return render_template('index.html', tasks=tasks)

# 路由：创建任务
@app.route('/tasks/create', methods=['GET', 'POST'])
@login_required
def create_task():
    if request.method == 'POST':
        task = Task(
            name=request.form['name'],
            cron_expression=request.form['cron_expression'],
            description=request.form['description'],
            script_content=request.form['script_content']
        )
        db.session.add(task)
        db.session.commit()
        
        # 更新crontab
        crontab_manager.add_or_update_job(task)
        flash('任务创建成功！', 'success')
        return redirect(url_for('index'))
    
    # 传递一个空的Task对象到模板
    task = Task()
    return render_template('task_form.html', task=task)

# 路由：编辑任务
@app.route('/tasks/<int:task_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_task(task_id):
    task = Task.query.get_or_404(task_id)
    if request.method == 'POST':
        task.name = request.form['name']
        task.cron_expression = request.form['cron_expression']
        task.description = request.form['description']
        task.script_content = request.form['script_content']
        db.session.commit()
        
        # 更新crontab
        crontab_manager.add_or_update_job(task)
        flash('任务更新成功！', 'success')
        return redirect(url_for('index'))
    
    return render_template('task_form.html', task=task)

# 路由：删除任务
@app.route('/tasks/<int:task_id>/delete', methods=['POST'])
@login_required
def delete_task(task_id):
    task = Task.query.get_or_404(task_id)
    
    # 从crontab中移除任务
    crontab_manager.remove_job(task.id)
    
    # 从数据库中删除任务
    db.session.delete(task)
    db.session.commit()
    
    flash('任务删除成功！', 'success')
    return redirect(url_for('index'))

if __name__ == '__main__':
    # 创建命令行参数解析器
    parser = argparse.ArgumentParser(description='备份任务管理系统')
    parser.add_argument('--host', default='127.0.0.1', help='监听的主机地址（默认：127.0.0.1）')
    parser.add_argument('--port', type=int, default=5000, help='监听的端口（默认：5000）')
    parser.add_argument('--debug', action='store_true', help='是否启用调试模式')
    args = parser.parse_args()

    # 创建数据库表
    with app.app_context():
        db.create_all()

    # 使用命令行参数启动应用
    app.run(
        host=args.host,
        port=args.port,
        debug=args.debug
    )