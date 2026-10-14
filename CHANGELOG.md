# Log de alterações do Bookspine

## Alpha 0.4 — 2026-10-14

Alterações em relação à versão `Alpha_0.3`.

### Adicionado

- Seletor **Chart** no Word Stats para alternar entre densidade **Density (KDE)** e gráfico de linhas **Line (token count)**.
- Contagem de tokens por intervalo do valor da métrica selecionada, ponderada pela coluna `book_count`.
- Controle **Frequency bins**, com padrão de 30 intervalos e limite de 1 a 200.

### Alterado

- O controle **Bandwidth** aparece no modo KDE; **Frequency bins** aparece no modo de contagem de tokens.
- O eixo vertical identifica **Density** ou **Token count**, conforme o gráfico selecionado.
- O novo gráfico utiliza os controles existentes de grupo, métrica, escalas, máximo de X e linhas de média e mediana.
- A mensagem de ausência de dados numéricos atende aos dois modos de gráfico.

### Escopo dos dados

- A contagem usa as linhas fornecidas ao gráfico após os filtros do Word Stats. Quando a tabela estiver limitada, o gráfico representa esse subconjunto.
- O máximo de X pode excluir intervalos de valores superiores do gráfico; média e mediana continuam calculadas sobre os valores válidos do grupo selecionado.

### Validação

- Suíte Python: 48 testes aprovados (`python -m unittest discover -s tests`).

## Alpha 0.3

Versão anterior, registrada pela tag `Alpha_0.3`, no commit `a2d1b40`.

- Classificação contextual das palavras com spaCy e o modelo `en_core_web_sm`.
- Controles de base de frequência e normalização por classe no visualizador.
- Atualização da documentação de instalação, métricas e uso.
- Inclusão das licenças e avisos de componentes de terceiros.

## Alpha 0.1

Versão inicial registrada pela tag `alpha-0.1`.
