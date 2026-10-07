# Publicação GitHub Pages + API

1. No repositório, abra Settings > Pages e escolha GitHub Actions como Source.
2. Execute o workflow "Publicar frontend no GitHub Pages" na aba Actions.
3. O endereço previsto é https://petitpedaco-bit.github.io/Finceiro-Petit-Pedaco/.
4. Crie um projeto gratuito PostgreSQL no Supabase e copie sua conexão de sessão
   (session pooler). Configure DATABASE_URL somente no Render, com o prefixo
   postgresql+asyncpg://. Nunca coloque a senha no GitHub ou em VITE_API_URL.
5. No Render, conecte este repositório usando New > Blueprint. O render.yaml
   configura a API no plano free. Informe DATABASE_URL quando solicitado.
6. Após a API iniciar, copie o endereço HTTPS do serviço. No GitHub, abra
   Settings > Secrets and variables > Actions > Variables e crie VITE_API_URL
   com esse endereço, sem /api ao final.
7. Execute novamente o workflow de Pages. Teste cadastro, venda e relatórios.

O frontend sozinho exibe a interface; as operações precisam da API e do banco.
Sem autenticação, o sistema e todas as operações são públicos. CORS não é login.
O plano gratuito da API pode suspender por inatividade. O banco remoto começa
vazio: dados do PostgreSQL local não são migrados automaticamente.
