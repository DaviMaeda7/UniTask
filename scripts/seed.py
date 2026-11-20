from pathlib import Path
import sys
import psycopg
from psycopg.rows import dict_row
from werkzeug.security import generate_password_hash

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config import DATABASE_URL


def main():
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as con:
        with con.transaction():
            users = [
                ('Mariana (fictícia)', 'mariana@exemplo.invalid', 'company'),
                ('Lucas (fictício)', 'lucas@exemplo.invalid', 'student')
            ]
            for name, email, role in users:
                con.execute("""INSERT INTO users(name,email,password_hash,role)
                               VALUES (%s,%s,%s,%s) ON CONFLICT (email) DO NOTHING""",
                            (name, email, generate_password_hash('DEMO-NAO-USAR'), role))
            mariana = con.execute('SELECT id FROM users WHERE email=%s', ('mariana@exemplo.invalid',)).fetchone()['id']
            lucas = con.execute('SELECT id FROM users WHERE email=%s', ('lucas@exemplo.invalid',)).fetchone()['id']
            con.execute("""INSERT INTO company_profiles(user_id,company_name,industry,description)
                           VALUES (%s,%s,%s,%s) ON CONFLICT (user_id) DO NOTHING""",
                        (mariana,'Cafeteria fictícia da Mariana','Alimentação','Negócio demonstrativo em Brasília'))
            con.execute("""INSERT INTO student_profiles(user_id,course,institution,skills)
                           VALUES (%s,%s,%s,%s) ON CONFLICT (user_id) DO NOTHING""",
                        (lucas,'Publicidade e Propaganda','UniCEUB','Canva, design, edição de vídeo'))
            projects = [
                ('Criação de 10 posts para Instagram','Criação de dez artes e legendas para uma cafeteria.','Marketing e design',25000,'2026-11-23','10 artes e 10 legendas'),
                ('Planilha de controle de estoque','Planilha simples para acompanhamento de produtos.','Planilhas e dados',20000,'2026-11-23','Planilha e instruções'),
                ('Landing page de demonstração','Página simples de apresentação de pequeno negócio.','Desenvolvimento web simples',45000,'2026-11-23','Página responsiva')
            ]
            for title,description,category,cents,deadline,deliverables in projects:
                if not con.execute('SELECT 1 FROM projects WHERE company_id=%s AND title=%s', (mariana,title)).fetchone():
                    con.execute("""INSERT INTO projects(company_id,title,description,category,amount_cents,deadline_date,deliverables)
                                   VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                                (mariana,title,description,category,cents,deadline,deliverables))
    print('Dados fictícios adicionados ao PostgreSQL. Nenhum pagamento realizado.')

if __name__ == '__main__':
    main()
