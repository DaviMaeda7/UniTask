# UniTask · Marketplace de microprojetos (MVP escolar)

Aplicação acadêmica em Flask e PostgreSQL, com perfis de estudantes e empresas, publicação de projetos, candidaturas, seleção, entrega, avaliações e **pagamentos exclusivamente simulados**.

## Tecnologias
Python 3 · Flask · PostgreSQL · Jinja2 / HTML / CSS · psycopg · Gunicorn.

## Executar localmente
1. Crie o ambiente virtual: `py -m venv .venv` (Windows).
2. Ative: `.\.venv\Scripts\Activate.ps1` (PowerShell).
3. Instale: `python -m pip install -r requirements.txt`.
4. Copie `.env.example` para `.env` e configure suas próprias credenciais. `.env` **não deve ir para o GitHub**.
5. Inicie ou configure um PostgreSQL existente. Se usar o Docker Compose, defina também `POSTGRES_PASSWORD` no `.env`. **Se já possui um banco com dados, não o recrie nem troque sua senha/volume às cegas.**
6. Para **um banco novo e vazio**, execute `python -m flask --app run.py init-db` e, opcionalmente, `python scripts/seed.py` para inserir exemplos. **Não execute esses comandos automaticamente sobre o banco que você já usa.**
7. Execute `python run.py` e abra http://127.0.0.1:5000.

## Publicação no Render (etapa seguinte)
- Build: `pip install -r requirements.txt`
- Start: `gunicorn run:app --bind 0.0.0.0:$PORT`
- Configure **no painel do Render**, e não no GitHub: `DATABASE_URL`, `SECRET_KEY`, `SESSION_COOKIE_SECURE=true`.
- Use uma instância PostgreSQL hospedada, **separada do banco Docker local**. Para um banco de produção novo e vazio, inicialize o esquema uma única vez por procedimento controlado.
- O aplicativo de demonstração precisa de revisão de segurança e privacidade antes de receber usuários reais ou dados pessoais.

## Segurança
- Não publique `.env`, credenciais, dados reais, exports ou logs.
- Antes de disponibilizar o repositório, revise `git status` e `git diff --cached --name-only`.
- Para a apresentação, use usuários e projetos fictícios.
- `SECRET_KEY` deve ser gerada com `python -c "import secrets; print(secrets.token_hex(32))"`.

## Código
- `app/__init__.py`: rotas, autenticação e regras de negócio
- `app/templates/`: HTML/Jinja
- `app/static/`: estilos, scripts e imagens
- `schema.sql`: estrutura PostgreSQL
- `scripts/seed.py`: dados demonstrativos
- `tests/`: testes
- `run.py`: inicialização local e ponto de entrada Gunicorn
