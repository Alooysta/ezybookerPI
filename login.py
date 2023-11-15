from flask import Flask, render_template, request, redirect, url_for, session
from flask_login import LoginManager, login_user, login_required, current_user, logout_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
import requests

app = Flask(__name__)
app.secret_key = '(INSERT YOUR KEY)'

login_manager = LoginManager(app)
login_manager.login_view = 'login'

# PARTE AIRTABLE
AIRTABLE_API_KEY = '(INSERT YOUR API)'
AIRTABLE_BASE_ID = '(INSERT YOUT BASE ID)'
AIRTABLE_TABLE_NAME = 'tudo'

AIRTABLE_API_ENDPOINT = f'https://api.airtable.com/v0/apprUVgE9R776w84G/tudo'
AIRTABLE_API_ENDPOINT_AGENDAMENTO = 'https://api.airtable.com/v0/appM3EIkjA8tn5aDm/horarios'

# ------ INÍCIO ROTAS ------

# ROTA INICIAL
@app.route('/')
def index():
    user = get_current_user()

    return render_template('index.html', user=user)


# ROTA PROFISSIONAIS
@app.route('/profissionais')
def pro():
    user = get_current_user()

    return render_template('pro.html', user=user)

# ROTA CHATBOT
@app.route('/chatbot')
def chatbot():
    user = get_current_user()

    return render_template('chatbot.html', user=user)

# ROTA SOBRE NÓS
@app.route('/sobre')
def sobre():
    user = get_current_user()

    return render_template('aboutus.html', user=user)    

# ROTA PLANOS
@app.route('/planos')
def planos():
    user = get_current_user()

    return render_template('plans.html', user=user)   

# ROTA REGISTRO
@app.route('/register', methods=['GET', 'POST'])
def register():
    error_message = None

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        role = 'client'
        name = request.form.get('name')
        phone = request.form.get('phone')
        document = request.form.get('document')
        birthdate = request.form.get('birthdate')

        try:
            create_user(username, password, role, name, phone, document, birthdate)
            return redirect(url_for('login'))

        except ValueError as e:
            error_message = str(e)

    return render_template('register.html', error_message=error_message)


# ROTA LOGIN
@app.route('/login', methods=['GET', 'POST'])
def login():
    error_message = None

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        user = find_user(username, password)

        if user:
            role = user.get('fields', {}).get('Role')

            if role:
                user_obj = User(user['id'], username, user['fields']['Password'], user['fields']['Nome'],
                                user['fields']['Telefone'], role)
                login_user(user_obj)
                return redirect(url_for('informacao') if role == 'client' else 'informacao')
            else:
                error_message = 'Invalid user role.'
        else:
            error_message = 'Nome de Usuário ou Senha errados. Por Favor, Tente novamente.'

    return render_template('login.html', error_message=error_message)


# ROTA DE INFORMAÇÃO
@app.route('/informacao')
@login_required
def informacao():
    user = current_user
    username = user.username

    if user.role == 'admin':
        params = {}
    else:
        params = {
            'filterByFormula': f'Username = "{username}"'
        }

    try:
        response = requests.get(AIRTABLE_API_ENDPOINT_AGENDAMENTO, params=params, headers=get_airtable_headers())
        response.raise_for_status()
        agendamentos = response.json().get('records', [])

        return render_template('informacao.html', user=user, agendamentos=agendamentos)

    except requests.exceptions.HTTPError as e:
        print(f"Erro ao obter agendamentos: {e}")
        return render_template('informacao.html', user=user, agendamentos=None)

#ROTAS LGPD
@app.route('/lgpd')
def lgpd():
    return render_template('lgpd.html')


# ROTA AGENDAR
@app.route('/agendar', methods=['GET', 'POST'])
@login_required
def agendar():
    error_message = None

    if request.method == 'POST':
        username = current_user.username
        data = request.form.get('data')
        horario = request.form.get('horario')
        sintomas = request.form.get('sintomas')

        # Verificar se a data já existe
        params_data = {
            'filterByFormula': f'AND(Username = "{username}", Data = "{data}")'
        }

        try:
            response_data = requests.get(AIRTABLE_API_ENDPOINT_AGENDAMENTO, params=params_data, headers=get_airtable_headers())
            response_data.raise_for_status()
            registros_data = response_data.json().get('records', [])

            # Verificar conflitos de horários
            for registro_data in registros_data:
                horario_existente = registro_data.get('fields', {}).get('Horario')
                if not verificar_disponibilidade(username, data, horario):
                    error_message = 'Data e horário já estão ocupados. Por favor, escolha outra data.'
                    break

            if not error_message:
                try:
                    create_agendamento(username, data, horario, sintomas)
                    return redirect(url_for('informacao'))

                except Exception as e:
                    print(f"Erro ao agendar: {e}")
                    error_message = 'O agendamento falhou. Por favor, tente novamente.'

        except Exception as e:
            print(f"Erro ao agendar: {e}")
            error_message = 'O agendamento falhou. Por favor, tente novamente.'

    return render_template('agendar.html', error_message=error_message)


# ROTA HORARIOS
@app.route('/horarios')
@login_required
def horarios():
    if current_user.role == 'admin':
        params = {}
    else:
        username = current_user.username
        params = {
            'filterByFormula': f'Username = "{username}"'
        }

    try:
        response = requests.get(AIRTABLE_API_ENDPOINT_AGENDAMENTO, params=params, headers=get_airtable_headers())
        response.raise_for_status()
        horarios = response.json().get('records', [])
        return render_template('horarios.html', horarios=horarios)

    except requests.exceptions.HTTPError as e:
        print(f"Erro ao obter horários: {e}")
        return render_template('horarios.html', horarios=None)



# ------ FIM ROTAS ------

#VERIFICAR SE USUÁRIO EXISTE (REGISTRO)
def user_exists(username):
    params = {
        'filterByFormula': f'Username = "{username}"'
    }
    try:
        response = requests.get(AIRTABLE_API_ENDPOINT, params=params, headers=get_airtable_headers())
        response.raise_for_status()
        records = response.json().get('records', [])
        return len(records) > 0
    except requests.exceptions.HTTPError as e:
        print(f"Erro ao verificar se o usuário existe: {e}")
        return False

# REGISTAR O USUÁRIO NO SITE DO AIRTABLE
def create_user(username, password, role, name, phone, document, birthdate):
    # Verificar se o username já existe
    if user_exists(username):
        raise ValueError('Usuário já existe. Por favor, escolha outro username.')

    # Se o username não existe, prosseguir com o registro
    data = {
        'fields': {
            'Username': username,
            'Password': password,
            'Role': role,
            'Nome': name,
            'Telefone': phone,
            'Documento': document,
            'Nascimento': birthdate
        }
    }
    try:
        response = requests.post(AIRTABLE_API_ENDPOINT, json=data, headers=get_airtable_headers())
        response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        print(f"Erro ao criar usuário no Airtable: {e}")
        raise ValueError('Erro no registro. Por favor, tente novamente.')

def find_user(username, password):
    params = {
        'filterByFormula': f'AND(Username = "{username}", Password = "{password}")'
    }
    try:
        response = requests.get(AIRTABLE_API_ENDPOINT, params=params, headers=get_airtable_headers())
        response.raise_for_status()
        records = response.json().get('records', [])
        return records[0] if records else None
    except requests.exceptions.HTTPError as e:
        print(f"Airtable API Error: {e}")
        return None

def get_airtable_headers():
    return {
        'Authorization': f'Bearer {AIRTABLE_API_KEY}',
        'Content-Type': 'application/json',
    }

class User(UserMixin):
    def __init__(self, user_id, username, password, nome, telefone, role, documento=None, nascimento=None):
        self.id = user_id
        self.username = username
        self.password = password
        self.nome = nome
        self.telefone = telefone
        self.role = role
        self.documento = documento
        self.nascimento = nascimento

    def check_password(self, password):
        return check_password_hash(self.password, password)

@login_manager.user_loader
def load_user(user_id):
    params = {
        'filterByFormula': f'RECORD_ID() = "{user_id}"'
    }

    try:
        response = requests.get(AIRTABLE_API_ENDPOINT, params=params, headers=get_airtable_headers())
        response.raise_for_status()
        record = response.json().get('records', [])[0]
        if record:
            return User(
                record['id'],
                record['fields']['Username'],
                record['fields']['Password'],
                record['fields']['Nome'],
                record['fields']['Telefone'],
                record['fields']['Role'],
                documento=record['fields'].get('Documento'),  # Adicione esta linha
                nascimento=record['fields'].get('Nascimento')  # Adicione esta linha
            )
    except requests.exceptions.HTTPError as e:
        print(f"Airtable API Error: {e}")

    return None


def get_current_user():
    username = session.get('username')

    if username:
        params = {
            'filterByFormula': f'Username = "{username}"'
        }

        try:
            response = requests.get(AIRTABLE_API_ENDPOINT, params=params, headers=get_airtable_headers())
            response.raise_for_status()
            records = response.json().get('records', [])
            return records[0] if records else None
        except requests.exceptions.HTTPError as e:
            print(f"Airtable API Error: {e}")

    return None

# REGISTRAR O AGENDAMENTO NO SITE DO AIRTABLE
def create_agendamento(username, data, horario, sintomas):
    data_agendamento = {
        'fields': {
            'Username': username,
            'Data': data,
            'Horario': horario,
            'Sintomas': sintomas
        }
    }
    response = requests.post(AIRTABLE_API_ENDPOINT_AGENDAMENTO, json=data_agendamento, headers=get_airtable_headers())
    response.raise_for_status()

# VERIFICA A DISPONIBILIDADE DE HORÁRIO
def verificar_disponibilidade(username, data, horario):
    params = {
        'filterByFormula': f'AND(Username = "{username}", Data = "{data}")'
    }

    try:
        response = requests.get(AIRTABLE_API_ENDPOINT_AGENDAMENTO, params=params, headers=get_airtable_headers())
        response.raise_for_status()
        registros = response.json().get('records', [])

        # VERIFICA CONFLITO DE HORÁRIOS
        for registro in registros:
            horario_existente = registro.get('fields', {}).get('Horario')
            if horario_existente == horario:
                return False  # TEVE CONFLITO

        return True  # NÃO TEVE CONFLITO

    except requests.exceptions.HTTPError as e:
        print(f"Erro ao verificar disponibilidade: {e}")
        return False



@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
