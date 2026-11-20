import os
import secrets
from datetime import date
from decimal import Decimal, InvalidOperation
from functools import wraps
from urllib.parse import urlparse
from flask import Flask, g, render_template, request, session, redirect, url_for, flash, abort
import psycopg
from psycopg import errors
from psycopg.rows import dict_row
from werkzeug.security import generate_password_hash, check_password_hash
from config import DATABASE_URL, SECRET_KEY


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(SECRET_KEY=SECRET_KEY, DATABASE_URL=DATABASE_URL,
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
                      SESSION_COOKIE_SECURE=os.getenv('SESSION_COOKIE_SECURE', 'false').lower() == 'true')
    if test_config:
        app.config.update(test_config)

    def db():
        if 'db' not in g:
            g.db = psycopg.connect(app.config['DATABASE_URL'], row_factory=dict_row, autocommit=True)
        return g.db

    @app.teardown_appcontext
    def close_db(error=None):
        connection = g.pop('db', None)
        if connection is not None:
            connection.close()

    @app.cli.command('init-db')
    def init_db():
        with app.open_resource('../schema.sql', mode='r') as file:
            schema = file.read()
        with db().transaction():
            db().execute(schema)
        print('Banco PostgreSQL do UniTask inicializado.')

    @app.before_request
    def load_user():
        g.user = None
        user_id = session.get('user_id')
        if user_id is not None:
            g.user = db().execute('SELECT id, name, email, role FROM users WHERE id=%s', (user_id,)).fetchone()
            if g.user is None:
                session.clear()

    @app.context_processor
    def shared_templates():
        if 'csrf_token' not in session:
            session['csrf_token'] = secrets.token_hex(24)
        return {'csrf_token': session['csrf_token']}

    def valid_csrf():
        token = request.form.get('csrf_token', '')
        if not token or not secrets.compare_digest(token, session.get('csrf_token', '')):
            abort(400, 'Token inválido. Atualize a página e tente novamente.')

    def login_required(view):
        @wraps(view)
        def protected(*args, **kwargs):
            if g.user is None:
                flash('Entre na sua conta para continuar.', 'warning')
                return redirect(url_for('login'))
            return view(*args, **kwargs)
        return protected

    @app.template_filter('brl')
    def brl(amount_cents):
        value = Decimal(amount_cents or 0) / 100
        return f"R$ {value:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

    @app.template_filter('brdate')
    def brdate(value):
        return value.strftime('%d/%m/%Y') if hasattr(value, 'strftime') else str(value)

    def company_required(view):
        @wraps(view)
        @login_required
        def protected(*args, **kwargs):
            if g.user['role'] != 'company':
                abort(403, 'Somente empresas podem publicar projetos.')
            return view(*args, **kwargs)
        return protected

    @app.get('/')
    def home():
        return render_template('home.html')

    CATEGORIES = ('Marketing e design', 'Planilhas e dados', 'Desenvolvimento web simples')

    @app.get('/projetos')
    def projects():
        category = request.args.get('categoria', '').strip()
        min_value = request.args.get('valor_min', '').strip()
        max_value = request.args.get('valor_max', '').strip()
        deadline = request.args.get('prazo_ate', '').strip()
        conditions = ["p.status='open'"]
        params = []
        if category in CATEGORIES:
            conditions.append('p.category=%s')
            params.append(category)
        elif category:
            flash('Categoria desconhecida; exibindo todas.', 'warning')
            category = ''
        for raw, column in ((min_value, 'p.amount_cents >= %s'), (max_value, 'p.amount_cents <= %s')):
            if raw:
                try:
                    parsed = Decimal(raw.replace(',', '.'))
                    if not parsed.is_finite() or parsed < 0 or parsed > 10000000:
                        raise InvalidOperation
                    conditions.append(column)
                    params.append(int(parsed * 100))
                except (InvalidOperation, ValueError):
                    flash('Filtro de valor ignorado: use um número positivo.', 'warning')
        if deadline:
            try:
                deadline_date = date.fromisoformat(deadline)
                conditions.append('p.deadline_date <= %s')
                params.append(deadline_date)
            except ValueError:
                flash('Filtro de prazo inválido.', 'warning')
        where = ' AND '.join(conditions)
        items = db().execute(f"""SELECT p.*, cp.company_name, u.name AS owner_name
            FROM projects p JOIN users u ON u.id=p.company_id
            LEFT JOIN company_profiles cp ON cp.user_id=p.company_id
            WHERE {where} ORDER BY p.created_at DESC, p.id DESC""", tuple(params)).fetchall()
        return render_template('projects.html', projects=items, category=category,
                               min_value=min_value, max_value=max_value, deadline=deadline,
                               categories=CATEGORIES)

    @app.route('/projetos/novo', methods=['GET', 'POST'])
    @company_required
    def create_project():
        values = {key: '' for key in ('title', 'description', 'category', 'amount', 'deadline', 'deliverables')}
        if request.method == 'POST':
            valid_csrf()
            values = {key: request.form.get(key, '').strip() for key in values}
            validation_error = None
            if not (5 <= len(values['title']) <= 120):
                validation_error = 'O título deve ter entre 5 e 120 caracteres.'
            elif not (15 <= len(values['description']) <= 3000):
                validation_error = 'A descrição deve ter entre 15 e 3000 caracteres.'
            elif values['category'] not in CATEGORIES:
                validation_error = 'Escolha uma categoria válida.'
            elif not (5 <= len(values['deliverables']) <= 2000):
                validation_error = 'Descreva os entregáveis (5 a 2000 caracteres).'
            else:
                try:
                    amount = Decimal(values['amount'].replace(',', '.'))
                    if not amount.is_finite() or amount < Decimal('1') or amount > Decimal('100000') or amount.as_tuple().exponent < -2:
                        raise InvalidOperation
                    amount_cents = int(amount * 100)
                except (InvalidOperation, ValueError):
                    validation_error = 'Informe um valor válido em reais, com no máximo duas casas decimais.'
            if not validation_error:
                try:
                    deadline_date = date.fromisoformat(values['deadline'])
                    if deadline_date < date.today():
                        validation_error = 'O prazo não pode estar no passado.'
                except ValueError:
                    validation_error = 'Informe uma data de entrega válida.'
            if validation_error:
                flash(validation_error, 'error')
            else:
                result = db().execute("""INSERT INTO projects
                    (company_id,title,description,category,amount_cents,deadline_date,deliverables)
                    VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (g.user['id'], values['title'], values['description'], values['category'],
                     amount_cents, deadline_date, values['deliverables'])).fetchone()
                flash('Projeto publicado com sucesso!', 'success')
                return redirect(url_for('project_detail', project_id=result['id']))
        return render_template('new_project.html', values=values, categories=CATEGORIES,
                               today=date.today().isoformat())

    @app.get('/projetos/<int:project_id>')
    def project_detail(project_id):
        item = db().execute("""SELECT p.*, cp.company_name, u.name AS owner_name
            FROM projects p JOIN users u ON u.id=p.company_id
            LEFT JOIN company_profiles cp ON cp.user_id=p.company_id
            WHERE p.id=%s""", (project_id,)).fetchone()
        if item is None:
            abort(404)
        applied = False
        if g.user and g.user['role'] == 'student':
            applied = db().execute('SELECT 1 FROM applications WHERE project_id=%s AND student_id=%s',
                                   (project_id, g.user['id'])).fetchone() is not None
        delivery = None
        payment = None
        my_review = None
        reviews = []
        can_access_private = bool(g.user and (g.user['id'] == item['company_id'] or g.user['id'] == item['selected_student_id']))
        if can_access_private:
            delivery = db().execute('SELECT * FROM deliveries WHERE project_id=%s', (project_id,)).fetchone()
            payment = db().execute('SELECT * FROM simulated_payments WHERE project_id=%s', (project_id,)).fetchone()
            my_review = db().execute('SELECT * FROM reviews WHERE project_id=%s AND reviewer_id=%s',
                                     (project_id, g.user['id'])).fetchone()
            reviews = db().execute('SELECT r.*, u.name AS reviewer_name FROM reviews r JOIN users u ON r.reviewer_id=u.id WHERE r.project_id=%s ORDER BY r.created_at',
                                   (project_id,)).fetchall()
        return render_template('project_detail.html', project=item, applied=applied, delivery=delivery,
                               payment=payment, my_review=my_review, reviews=reviews,
                               can_access_private=can_access_private)

    @app.get('/meus-projetos')
    @company_required
    def my_projects():
        items = db().execute("""SELECT * FROM projects WHERE company_id=%s
            ORDER BY created_at DESC, id DESC""", (g.user['id'],)).fetchall()
        return render_template('my_projects.html', projects=items)

    def student_required(view):
        @wraps(view)
        @login_required
        def protected(*args, **kwargs):
            if g.user['role'] != 'student':
                abort(403, 'Somente estudantes podem se candidatar.')
            return view(*args, **kwargs)
        return protected

    @app.post('/projetos/<int:project_id>/candidatar')
    @student_required
    def apply_project(project_id):
        valid_csrf()
        message = request.form.get('message', '').strip()
        if not (10 <= len(message) <= 1000):
            flash('Escreva uma apresentação de 10 a 1000 caracteres.', 'error')
            return redirect(url_for('project_detail', project_id=project_id))
        with db().transaction():
            project = db().execute('SELECT id,status FROM projects WHERE id=%s FOR UPDATE', (project_id,)).fetchone()
            if project is None:
                abort(404)
            if project['status'] != 'open':
                flash('Este projeto não aceita novas candidaturas.', 'warning')
                return redirect(url_for('project_detail', project_id=project_id))
            exists = db().execute('SELECT id FROM applications WHERE project_id=%s AND student_id=%s',
                                  (project_id, g.user['id'])).fetchone()
            if exists:
                flash('Você já se candidatou a este projeto.', 'warning')
                return redirect(url_for('project_detail', project_id=project_id))
            db().execute('INSERT INTO applications (project_id,student_id,message) VALUES (%s,%s,%s)',
                         (project_id, g.user['id'], message))
        flash('Candidatura enviada com sucesso!', 'success')
        return redirect(url_for('my_applications'))

    @app.get('/minhas-candidaturas')
    @student_required
    def my_applications():
        applications = db().execute("""SELECT a.id, a.message, a.created_at, p.id AS project_id,
                       p.title, p.status, p.selected_student_id, p.amount_cents, p.deadline_date
                       FROM applications a JOIN projects p ON p.id=a.project_id
                       WHERE a.student_id=%s ORDER BY a.created_at DESC, a.id DESC""",
                       (g.user['id'],)).fetchall()
        return render_template('my_applications.html', applications=applications)

    @app.get('/projetos/<int:project_id>/candidaturas')
    @company_required
    def project_applications(project_id):
        project = db().execute('SELECT * FROM projects WHERE id=%s AND company_id=%s',
                               (project_id, g.user['id'])).fetchone()
        if project is None:
            abort(404)
        applications = db().execute("""SELECT a.id, a.student_id, a.message, a.created_at,
            u.name, sp.course, sp.institution, sp.skills, sp.portfolio_url
            FROM applications a JOIN users u ON u.id=a.student_id
            LEFT JOIN student_profiles sp ON sp.user_id=u.id
            WHERE a.project_id=%s ORDER BY a.created_at ASC, a.id ASC""", (project_id,)).fetchall()
        return render_template('project_applications.html', project=project, applications=applications)

    @app.post('/projetos/<int:project_id>/selecionar/<int:application_id>')
    @company_required
    def select_applicant(project_id, application_id):
        valid_csrf()
        with db().transaction():
            project = db().execute('SELECT id,status FROM projects WHERE id=%s AND company_id=%s FOR UPDATE',
                                   (project_id, g.user['id'])).fetchone()
            if project is None:
                abort(404)
            if project['status'] != 'open':
                flash('Este projeto já foi iniciado ou encerrado.', 'warning')
                return redirect(url_for('project_applications', project_id=project_id))
            candidate = db().execute("""SELECT a.student_id FROM applications a
                                      JOIN users u ON u.id=a.student_id
                                      WHERE a.id=%s AND a.project_id=%s AND u.role='student'""",
                                      (application_id, project_id)).fetchone()
            if candidate is None:
                abort(404)
            db().execute("""UPDATE projects SET selected_student_id=%s, status='in_progress'
                            WHERE id=%s""", (candidate['student_id'], project_id))
        flash('Estudante selecionado! O projeto agora está em andamento.', 'success')
        return redirect(url_for('project_detail', project_id=project_id))

    # Dia 20: entrega -> aprovação -> pagamento DEMONSTRATIVO -> avaliações.
    @app.post('/projetos/<int:project_id>/entregar')
    @student_required
    def submit_delivery(project_id):
        valid_csrf()
        delivery_url = request.form.get('delivery_url', '').strip()
        parsed = urlparse(delivery_url)
        if (len(delivery_url) > 1000 or parsed.scheme not in ('https', 'http') or
                not parsed.hostname or parsed.username or parsed.password):
            flash('Informe um link válido de entrega (http ou https; até 1000 caracteres).', 'error')
            return redirect(url_for('project_detail', project_id=project_id))
        with db().transaction():
            project = db().execute('SELECT id,status,selected_student_id FROM projects WHERE id=%s FOR UPDATE',
                                   (project_id,)).fetchone()
            if project is None:
                abort(404)
            if project['selected_student_id'] != g.user['id']:
                abort(403)
            if project['status'] != 'in_progress':
                flash('Este projeto não está disponível para uma nova entrega.', 'warning')
                return redirect(url_for('project_detail', project_id=project_id))
            db().execute('INSERT INTO deliveries(project_id,student_id,delivery_url) VALUES (%s,%s,%s)',
                         (project_id, g.user['id'], delivery_url))
            db().execute("UPDATE projects SET status='delivered' WHERE id=%s", (project_id,))
        flash('Entrega registrada! Aguardando aprovação da empresa.', 'success')
        return redirect(url_for('project_detail', project_id=project_id))

    @app.post('/projetos/<int:project_id>/aprovar')
    @company_required
    def approve_delivery(project_id):
        valid_csrf()
        with db().transaction():
            project = db().execute('SELECT id,company_id,amount_cents,status FROM projects WHERE id=%s FOR UPDATE',
                                   (project_id,)).fetchone()
            if project is None:
                abort(404)
            if project['company_id'] != g.user['id']:
                abort(403)
            if project['status'] != 'delivered':
                flash('A aprovação só é possível após o envio da entrega.', 'warning')
                return redirect(url_for('project_detail', project_id=project_id))
            delivery = db().execute('SELECT id FROM deliveries WHERE project_id=%s',
                                    (project_id,)).fetchone()
            if delivery is None:
                abort(409, 'Entrega não encontrada.')
            db().execute('UPDATE deliveries SET approved_at=CURRENT_TIMESTAMP WHERE project_id=%s AND approved_at IS NULL',
                         (project_id,))
            db().execute("UPDATE projects SET status='completed' WHERE id=%s", (project_id,))
            # Nenhuma operação com bancos, Pix ou APIs financeiras.
            db().execute("""INSERT INTO simulated_payments(project_id,amount_cents,commission_percent,label)
                            VALUES (%s,%s,%s,%s)""",
                         (project_id, project['amount_cents'], 12,
                          'SIMULADO — nenhuma cobrança, transferência ou recebimento real'))
        flash('Entrega aprovada! Pagamento fictício registrado para demonstração.', 'success')
        return redirect(url_for('project_detail', project_id=project_id))

    @app.post('/projetos/<int:project_id>/avaliar')
    @login_required
    def review_project(project_id):
        valid_csrf()
        try:
            rating = int(request.form.get('rating', ''))
        except ValueError:
            rating = 0
        comment = request.form.get('comment', '').strip()
        if rating not in range(1, 6) or len(comment) > 1000:
            flash('Escolha uma nota entre 1 e 5 e escreva no máximo 1000 caracteres.', 'error')
            return redirect(url_for('project_detail', project_id=project_id))
        with db().transaction():
            project = db().execute("""SELECT id, status, company_id, selected_student_id
                                      FROM projects WHERE id=%s FOR UPDATE""", (project_id,)).fetchone()
            if project is None:
                abort(404)
            if project['status'] != 'completed':
                flash('Avaliações são liberadas após a aprovação da entrega.', 'warning')
                return redirect(url_for('project_detail', project_id=project_id))
            if g.user['id'] == project['company_id']:
                reviewee_id = project['selected_student_id']
            elif g.user['id'] == project['selected_student_id']:
                reviewee_id = project['company_id']
            else:
                abort(403)
            exists = db().execute('SELECT id FROM reviews WHERE project_id=%s AND reviewer_id=%s',
                                  (project_id, g.user['id'])).fetchone()
            if exists:
                flash('Você já avaliou este projeto.', 'warning')
                return redirect(url_for('project_detail', project_id=project_id))
            db().execute("""INSERT INTO reviews(project_id,reviewer_id,reviewee_id,rating,comment)
                            VALUES (%s,%s,%s,%s,%s)""",
                         (project_id, g.user['id'], reviewee_id, rating, comment))
        flash('Avaliação registrada. Obrigado!', 'success')
        return redirect(url_for('project_detail', project_id=project_id))

    @app.get('/entrar')
    def auth():
        if g.user:
            return redirect(url_for('home'))
        mode = 'register' if request.args.get('modo') == 'cadastro' else 'login'
        return render_template('auth.html', mode=mode)

    @app.route('/cadastro', methods=['GET', 'POST'])
    def register():
        if g.user:
            return redirect(url_for('home'))
        if request.method == 'GET':
            return redirect(url_for('auth', modo='cadastro'))
        if request.method == 'POST':
            valid_csrf()
            name = request.form.get('name', '').strip()
            email = request.form.get('email', '').strip().lower()
            password = request.form.get('password', '')
            role = request.form.get('role', '')
            if not name or len(name) > 120 or not email or len(email) > 254 or '@' not in email or role not in ('student','company'):
                flash('Preencha nome, e-mail e tipo de conta corretamente.', 'error')
            elif len(password) < 8 or len(password) > 128:
                flash('A senha deve ter entre 8 e 128 caracteres.', 'error')
            else:
                try:
                    with db().transaction():
                        user = db().execute('INSERT INTO users(name,email,password_hash,role) VALUES (%s,%s,%s,%s) RETURNING id',
                                            (name, email, generate_password_hash(password), role)).fetchone()
                        if role == 'student':
                            db().execute('INSERT INTO student_profiles(user_id) VALUES (%s)', (user['id'],))
                        else:
                            db().execute('INSERT INTO company_profiles(user_id,company_name) VALUES (%s,%s)', (user['id'], name))
                    session.clear()
                    session['user_id'] = user['id']
                    session['csrf_token'] = secrets.token_hex(24)
                    flash('Conta criada! Bem-vindo ao UniTask. Você pode completar seu perfil pelo menu.', 'success')
                    return redirect(url_for('home'))
                except errors.UniqueViolation:
                    flash('Este e-mail já está cadastrado.', 'error')
        return render_template('auth.html', mode='register')

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if g.user:
            return redirect(url_for('home'))
        if request.method == 'GET':
            return redirect(url_for('auth'))
        if request.method == 'POST':
            valid_csrf()
            email = request.form.get('email', '').strip().lower()
            password = request.form.get('password', '')
            user = db().execute('SELECT id,password_hash FROM users WHERE email=%s', (email,)).fetchone()
            if user is None or not check_password_hash(user['password_hash'], password):
                flash('E-mail ou senha inválidos.', 'error')
            else:
                session.clear()
                session['user_id'] = user['id']
                session['csrf_token'] = secrets.token_hex(24)
                flash('Bem-vindo ao UniTask!', 'success')
                return redirect(url_for('home'))
        return render_template('auth.html', mode='login')

    @app.post('/logout')
    @login_required
    def logout():
        valid_csrf()
        session.clear()
        flash('Você saiu da sua conta.', 'success')
        return redirect(url_for('home'))

    def reputation_summary(user_id):
        """Nota estimada: começa em 5,0 com peso inicial equivalente a duas notas.
        Não representa duas avaliações reais; a contagem real é apresentada ao lado.
        """
        row = db().execute(
            'SELECT COUNT(*) AS total, COALESCE(SUM(rating), 0) AS points FROM reviews WHERE reviewee_id=%s',
            (user_id,)).fetchone()
        count = int(row['total'])
        score = (10 + int(row['points'])) / (2 + count)
        return {'score': f'{score:.1f}'.replace('.', ','), 'count': count,
                'is_initial': count == 0}

    @app.get('/perfil')
    @login_required
    def profile():
        role = g.user['role']
        table = 'student_profiles' if role == 'student' else 'company_profiles'
        details = db().execute(f'SELECT * FROM {table} WHERE user_id=%s', (g.user['id'],)).fetchone()
        return render_template('profile_view.html', profile=details or {}, role=role,
                               reputation=reputation_summary(g.user['id']))

    @app.route('/perfil/editar', methods=['GET', 'POST'])
    @login_required
    def edit_profile():
        role = g.user['role']
        if request.method == 'POST':
            valid_csrf()
            fields = ['course', 'institution', 'skills', 'portfolio_url'] if role == 'student' else ['company_name', 'industry', 'description']
            values = {field: request.form.get(field, '').strip() for field in fields}
            if any(len(v) > 1000 for v in values.values()):
                flash('Um dos campos ultrapassa o limite de 1000 caracteres.', 'error')
            elif role == 'company' and not values['company_name']:
                flash('O nome da empresa é obrigatório.', 'error')
            elif role == 'student' and values['portfolio_url'] and not values['portfolio_url'].startswith(('https://', 'http://')):
                flash('O portfólio deve começar por https:// ou http://.', 'error')
            else:
                if role == 'student':
                    db().execute('UPDATE student_profiles SET course=%s,institution=%s,skills=%s,portfolio_url=%s WHERE user_id=%s',
                                 (values['course'],values['institution'],values['skills'],values['portfolio_url'],g.user['id']))
                else:
                    db().execute('UPDATE company_profiles SET company_name=%s,industry=%s,description=%s WHERE user_id=%s',
                                 (values['company_name'],values['industry'],values['description'],g.user['id']))
                flash('Perfil atualizado!', 'success')
                return redirect(url_for('profile'))
        table = 'student_profiles' if role == 'student' else 'company_profiles'
        details = db().execute(f'SELECT * FROM {table} WHERE user_id=%s', (g.user['id'],)).fetchone()
        return render_template('profile.html', profile=details or {}, role=role)

    @app.get('/saude')
    def health():
        return {'status':'ok','project':'UniTask','database':'PostgreSQL','stage':'refinamento visual e UX (dia 21)'}

    return app
