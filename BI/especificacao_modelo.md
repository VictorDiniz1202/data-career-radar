# Especificação do Modelo Power BI — Data Career Radar

Guia para montar **manualmente** o modelo semântico em `BI/BI.pbix` a partir do PostgreSQL local. O `.pbix` é binário e está no `.gitignore`; este documento é a fonte versionada do modelo.

**Estado:** especificação. Nenhuma página, visual ou medida foi criada no `.pbix` por esta sprint; as medidas abaixo só estarão verificadas depois que forem montadas e conferidas contra as consultas SQL de validação (seção 6).

---

## 1. Pré-requisitos

| Item | Detalhe |
|---|---|
| Banco no ar | `docker compose up -d` (ou `./run.sh`). Host `localhost`, porta `5433`, banco `radar_db`, usuário `radar_user`. A senha está no `.env` local; **não a copie para este documento nem para o `.pbix` compartilhado**. |
| Dados | Rodar `./run.sh` (ou ingest + classify) antes de importar. Sem `classify`, vagas antigas ficam com `is_data_role` em branco. |
| Driver | O Power BI Desktop já inclui o provedor Npgsql desde dez/2019 (v4.0.17 a partir de out/2024); não instalar nada extra em versões atuais. Em versões antigas, instalar o Npgsql 4.0.17 com a opção *GAC Installation* (a série 4.1+ não é suportada). Fonte: [Power Query PostgreSQL connector](https://learn.microsoft.com/en-us/power-query/connectors/postgresql), consultada em 2026-10-07. |
| Alternativa ODBC | Só se o conector nativo falhar: driver `psqlODBC` (64 bits) + *Get Data → ODBC*. O modelo abaixo não muda. |

## 2. Conexão (passo a passo)

1. Power BI Desktop → abrir `BI/BI.pbix`.
2. **Obter dados → Banco de dados PostgreSQL**.
3. Servidor: `localhost:5433` · Banco de dados: `radar_db` · Modo: **Importar** (o volume é pequeno; DirectQuery não agrega valor).
4. Em **Opções avançadas → Instrução SQL**, colar a consulta da seção 3.
5. Autenticação **Banco de dados**: usuário `radar_user` e a senha do `.env`.
6. Aviso de conexão não criptografada: é o Postgres local em Docker; aceitar **OK**.
7. **Transformar dados** (não *Carregar*) para aplicar os ajustes da seção 3.

## 3. Tabela fato `fato_vagas`

Consulta SQL (exclui `content`, HTML bruto grande que o modelo não usa):

```sql
SELECT id, source, board_slug, external_id, title, location,
       is_remote, country_code, url,
       updated_at, first_seen_at, last_seen_at,
       is_data_role,
       match_score, salary_extracted, match_reason, match_model, evaluated_at
FROM job_postings
```

Ajustes no Power Query:

| Coluna | Tipo no Power BI | Observação |
|---|---|---|
| `id` | Número inteiro | Chave da linha. |
| `is_remote`, `is_data_role` | Verdadeiro/Falso | `is_data_role` em branco = ainda não classificada (rodar `classify`). |
| `country_code` | Texto | **Em branco = localização desconhecida**, não "fora do Brasil". Não substituir por valor padrão. |
| `match_score` | Número inteiro | Em branco = não avaliada. Não preencher com 0. |
| `first_seen_at`, `last_seen_at`, `evaluated_at` | Data/Hora | |
| `empresa_key` (nova) | Texto | `[source] & "|" & [board_slug]`, usada na relação com `dim_empresa`. |
| `data_primeira_vez` (nova) | Data | `Date.From([first_seen_at])`, usada na relação com `dim_calendario`. |

Marcar `url` como **Categoria de dados: URL da Web** para habilitar o link no visual de tabela.

## 4. Modelo em estrela

```
dim_calendario (1) ───< fato_vagas >─── (1) dim_empresa
   data                  id                 empresa_key
                         data_primeira_vez  source
                         empresa_key        board_slug
```

- **`fato_vagas`**: uma linha por vaga (`id`), carga atual de `job_postings`.
- **`dim_empresa`**: no Power Query, *Referenciar* `fato_vagas` → manter `empresa_key`, `source`, `board_slug` → remover duplicatas.
- **`dim_calendario`**: tabela DAX, marcada como tabela de datas:
  ```dax
  dim_calendario =
  ADDCOLUMNS (
      CALENDAR ( MIN ( fato_vagas[data_primeira_vez] ), TODAY () ),
      "ano_mes", FORMAT ( [Date], "YYYY-MM" )
  )
  ```
  (renomear a coluna `Date` para `data`).
- **Relações** (todas *um-para-muitos*, filtro dimensão → fato, direção única):
  - `dim_calendario[data]` → `fato_vagas[data_primeira_vez]`
  - `dim_empresa[empresa_key]` → `fato_vagas[empresa_key]`

Com uma única fonte, a estrela é enxuta de propósito. Novas dimensões (país, família de cargo) entram quando houver um segundo atributo que justifique.

## 5. Medidas DAX iniciais

Criar numa tabela vazia `_Medidas` (*Inserir dados*) para manter o painel organizado.

```dax
Total Vagas = COUNTROWS ( fato_vagas )

Vagas de Dados =
CALCULATE ( [Total Vagas], fato_vagas[is_data_role] = TRUE () )

Vagas Elegíveis BR =
CALCULATE ( [Vagas de Dados], fato_vagas[country_code] = "BR" )

Vagas a Revisar (País Desconhecido) =
CALCULATE ( [Vagas de Dados], ISBLANK ( fato_vagas[country_code] ) )

Vagas Avaliadas =
CALCULATE ( COUNT ( fato_vagas[match_score] ), fato_vagas[is_data_role] = TRUE () )

Nota Média =
CALCULATE ( AVERAGE ( fato_vagas[match_score] ), fato_vagas[is_data_role] = TRUE () )

Cobertura de Avaliação = DIVIDE ( [Vagas Avaliadas], [Vagas de Dados] )
```

Leitura correta das medidas (regras do domínio do projeto):

- **Vagas Elegíveis BR** conta vagas de dados com localização identificada como Brasil. É um **filtro de localização, não confirmação de elegibilidade de contratação**: remoto não prova residência aceita. O nome vem da especificação da sprint; se preferir, renomear para *Vagas de Dados com Local BR*.
- **Vagas a Revisar** é a outra metade do funil: localização desconhecida exige revisão manual (o `evaluate` também as mantém).
- **Nota Média** considera só vagas de dados e ignora as não avaliadas (BLANK); avaliações antigas de vagas hoje marcadas como fora da área (feitas antes do pré-filtro) ficam de fora. A nota é **prioridade de esforço de revisão, não chance de contratação**, e ainda não foi calibrada contra o baseline humano. Exibir sempre junto com *Vagas Avaliadas*; com poucas avaliações a média engana.
- `is_data_role` vem de um filtro por palavras no título e aceita falsos positivos (ex.: títulos que citam "Machine Learning" ou "Analytics" sem ser da área). Não é classificação de senioridade nem de aderência.

## 6. Validação do modelo (após montar)

Conferir cada medida contra o banco antes de declará-la correta:

```sql
SELECT count(*)                                           AS total_vagas,
       count(*) FILTER (WHERE is_data_role)               AS vagas_de_dados,
       count(*) FILTER (WHERE is_data_role
                        AND country_code = 'BR')          AS elegiveis_br,
       count(*) FILTER (WHERE is_data_role
                        AND country_code IS NULL)         AS a_revisar,
       count(match_score) FILTER (WHERE is_data_role)     AS avaliadas,
       round(avg(match_score) FILTER (WHERE is_data_role), 2) AS nota_media
FROM job_postings;
```

Os cartões do Power BI devem bater com a linha retornada. Registrar a data e o resultado em `docs/competency-evidence.md` somente depois dessa conferência.

## 7. Atualização e limites

- Após cada execução do pipeline: **Página Inicial → Atualizar** no Power BI Desktop. Não há atualização agendada (banco local).
- O `.pbix` não é versionado (`*.pbix` no `.gitignore`); este documento é a referência para reconstruí-lo.
- Página/visuais, tema e layout ficam para uma etapa própria (skill `powerbi-design`). Esta especificação cobre apenas conexão, modelo e medidas.
