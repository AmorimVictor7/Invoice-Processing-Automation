# PRD — Automação de Processamento de Invoices Internacionais

## Nome do Produto

**Invoice Processing Automation**

---

## Visão Geral do Produto

A aplicação terá como objetivo automatizar o processamento mensal de invoices internacionais referentes à contratação de ferramentas e serviços de fornecedores estrangeiros.

Atualmente, o processo é realizado manualmente:

- O colaborador recebe ou baixa o invoice
- Abre o documento
- Digita os dados manualmente em uma planilha
- Renomeia o arquivo
- Organiza os arquivos em pastas
- Envia tudo ao financeiro

Esse fluxo consome tempo operacional, aumenta o risco de erros humanos e dificulta a padronização das informações.

A solução proposta permitirá:

- Upload do invoice
- Leitura automática do documento
- Extração estruturada dos dados
- Preenchimento automático da planilha padrão
- Renomeação automática dos arquivos
- Organização automática em pastas
- Preparação do material para envio ao financeiro

---

## Objetivo da Fase 1

Automatizar o cadastro de invoices em planilha padrão e organizar os arquivos em estrutura pronta para envio ao departamento financeiro.

---

## Problema a Ser Resolvido

O processo manual atual apresenta:

- Alto tempo de execução
- Erros de digitação
- Inconsistência entre arquivos e planilha
- Dificuldade de rastreabilidade
- Dependência de conhecimento individual
- Baixa escalabilidade para aumento do volume mensal

---

## Objetivos de Negócio

- Reduzir o tempo operacional do processo em pelo menos 80%
- Reduzir erros manuais de preenchimento
- Padronizar informações financeiras
- Melhorar rastreabilidade documental
- Facilitar auditorias futuras
- Criar base para evolução futura com integração ERP

---

## Usuários

### Usuário Principal

Analista responsável pelo envio mensal de invoices ao financeiro.

### Usuário Secundário

Gestores administrativos ou financeiros que validam o processo.

---

## Escopo Funcional da Fase 1

A aplicação deverá permitir:

### Upload de Documentos

O usuário poderá enviar um ou múltiplos arquivos invoice nos formatos:

- PDF
- PNG
- JPG
- JPEG

### Leitura Inteligente do Documento

O sistema deverá extrair automaticamente:

- Nome do fornecedor
- Invoice number
- Data de emissão
- Período de cobrança
- Valor total
- Moeda
- Descrição do serviço
- Taxas adicionais
- Subtotal
- Impostos, se existirem
- Valor final

### Validação de Dados

Antes da gravação:

- Mostrar os dados extraídos em tela
- Permitir correção manual
- Destacar campos com baixa confiança da leitura
- Permitir confirmação do usuário

### Geração da Planilha

A aplicação deverá preencher automaticamente uma planilha padrão contendo:

- Fornecedor
- Número da invoice
- Data da invoice
- Descrição
- Moeda original
- Valor original
- Cotação manual ou fixa
- Valor convertido em BRL
- Centro de custo
- Observações
- Nome do arquivo final

### Organização Automática dos Arquivos

Após confirmação:

- Renomear os arquivos automaticamente
- Mover para pasta organizada

#### Estrutura sugerida

```text
Ano/
└── Mês/
    └── Fornecedor/

Exemplo:
2026/
└── 04_Abril/
    ├── Google/
    ├── Meta/
    └── OpenAI/

#### Padrão do nome do arquivo
FORNECEDOR_NUMEROINVOICE_DATA_VALOR.pdf

Exemplo
GOOGLE_INV12345_2026-04-10_250USD.pdf

Exportação Final

A aplicação deverá gerar:
- Planilha consolidada em Excel
- Pasta compactada com invoices organizadas
- Arquivo pronto para envio ao financeiro
- Fluxo do Usuário
- Usuário acessa o sistema
- Usuário realiza upload dos invoices
- Sistema processa OCR e extração
- Sistema exibe dados para revisão
- Usuário confirma ou corrige
- Sistema grava dados na planilha
- Sistema renomeia arquivos
- Sistema organiza pastas
- Sistema disponibiliza download do pacote final

Requisitos Funcionais
| Código | Descrição                                          |
| ------ | -------------------------------------------------- |
| RF001  | Permitir upload individual de invoices             |
| RF002  | Suportar arquivos PDF e imagens                    |
| RF003  | Extrair dados automaticamente via OCR ou parser    |
| RF004  | Permitir edição manual antes da confirmação        |
| RF005  | Gerar planilha Excel padronizada                   |
| RF006  | Renomear arquivos automaticamente                  |
| RF007  | Organizar documentos em pastas                     |
| RF008  | Permitir download do pacote final                  |
| RF009  | Registrar histórico do processamento realizado     |
| RF010  | Exibir mensagens de erro para documentos inválidos |

Requisitos Não Funcionais
| Código | Descrição                                                        |
| ------ | ---------------------------------------------------------------- |
| RNF001 | Interface simples e intuitiva                                    |
| RNF002 | Tempo máximo de processamento por invoice inferior a 10 segundos |
| RNF003 | Armazenamento temporário seguro                                  |
| RNF004 | Compatível com navegador desktop                                 |
| RNF005 | Permitir expansão futura para integração com ERP                 |
| RNF006 | Logs para auditoria                                              |

Regras de Negócio
| Código | Regra                                                                         |
| ------ | ----------------------------------------------------------------------------- |
| RN001  | Cada invoice deve gerar uma única linha na planilha                           |
| RN002  | Se um invoice estiver duplicado, o sistema deve alertar                       |
| RN003  | Campos obrigatórios: fornecedor, número, data, valor e moeda                  |
| RN004  | Se o OCR não identificar um campo obrigatório, solicitar preenchimento manual |
| RN005  | Arquivos só podem ser exportados após validação do usuário                    |

#### Campos da Planilha Padrão
A planilha final deverá conter as seguintes colunas:
- Data do processamento
- Fornecedor
- Invoice number
- Data de emissão
- Descrição
- Moeda
- Valor original
- Cotação
- Valor convertido
- Centro de custo
- Observações
- Arquivo vinculado

---

# Configuração Inicial do Ambiente (.env)

A aplicação deverá utilizar variáveis de ambiente para armazenamento de credenciais e configurações sensíveis.

## Exemplo `.env`


OCR_PROVIDER=google

GOOGLE_VISION_API_KEY=your_api_key_here

STORAGE_PROVIDER=sharepoint

SHAREPOINT_CLIENT_ID=your_client_id
SHAREPOINT_CLIENT_SECRET=your_secret

DATABASE_URL=

TEMP_STORAGE_PATH=

APP_ENV=development

SERVER_PORT=8000

---

## Arquivo `.env.example`


OCR_PROVIDER=

GOOGLE_VISION_API_KEY=

STORAGE_PROVIDER=

SHAREPOINT_CLIENT_ID=
SHAREPOINT_CLIENT_SECRET=

DATABASE_URL=

TEMP_STORAGE_PATH=

APP_ENV=

SERVER_PORT=


---


#### Tecnologia Sugerida
Frontend
- React
- Next.js
Backend
- Node.js
- Python FastAPI
OCR
- Google Vision API
- AWS Textract
- Tesseract OCR
Manipulação de Excel
- Python openpyxl
- Node exceljs
Armazenamento Temporário dos arquivos
- Onedrive, Sharepoint ou S3

#### Futuras Evoluções 
- Integração direta com ERP
- Cotação automática de moeda
- Aprovação do financeiro dentro do sistema
- Envio automático por e-mail
- Dashboard de despesas por fornecedor
- Detecção inteligente de duplicidade
- Classificação automática por centro de custo