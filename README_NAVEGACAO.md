# UniTask — refinamento final do cabeçalho

Esta versão aplica sublinhado roxo ao item ativo do menu, transição ao passar o mouse e animação suave de entrada ao navegar entre páginas. O destaque acompanha Início, Projetos e detalhes, Meus projetos e candidaturas da empresa, Publicar projeto, Minhas candidaturas, Meu perfil e sua edição, e Entrar. Respeita `prefers-reduced-motion`.

## Instalação
1. Pare o Flask e faça backup da pasta atual.
2. Copie apenas `app/templates/base.html` e `app/static/style.css` para os mesmos caminhos no projeto atual.
3. Preserve `.env`, banco PostgreSQL, demais arquivos e dados.
4. Inicie `python run.py` e atualize com Ctrl+F5 no navegador.

Não requer alteração do PostgreSQL nem execução de seed/init-db.
