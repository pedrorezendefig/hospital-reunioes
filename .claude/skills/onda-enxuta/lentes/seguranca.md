# Lente de segurança

Entra quando o PR toca login, permissão, rota ou segredo. Olhe só as linhas do diff e quem as chama. É must-fix:

- **Autenticação:** rota ou ação nova, ou mudada, que responde sem conferir a sessão; login que aceita token vencido ou sem assinatura conferida.
- **Permissão de rota:** confere o login mas não o perfil ou o dono do recurso (o id da URL abre o dado de outra pessoa); erro de acesso que sai como 500 em vez de 401 ou 403.
- **Consulta montada com texto do usuário:** SQL, comando de shell, caminho de arquivo ou URL montados por concatenação com o que veio da requisição, sem parâmetro nem validação.
- **Segredo em log:** token, senha, chave ou cabeçalho `Authorization` em log, mensagem de erro, resposta ou código do navegador; segredo escrito no código.
- **Regras de acesso do banco:** tabela nova sem RLS, política que libera tudo (`using (true)`) ou chave de serviço usada no cliente.
