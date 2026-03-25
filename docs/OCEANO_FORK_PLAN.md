# Oceano Now Playing - Plano Completo de Extracao

## Objetivo
Transformar este fork em uma distribuicao focada exclusivamente no Oceano (AirPlay via metadata pipe do shairport-sync), removendo suporte a Volumio, Moode e piCorePlayer.

Resultado esperado:
- Projeto mais simples e alinhado ao ecosistema oceano-player (Go).
- Menos superficie de manutencao.
- Contrato claro: oceano-player produz metadata, oceano-now-playing renderiza display.

## Escopo
### Dentro do escopo
- Manter renderer/framebuffer e state machine.
- Manter cliente Oceano.
- Simplificar configuracao para Oceano-only.
- Atualizar testes e documentacao.
- Ajustar empacotamento e scripts para novo foco.

### Fora do escopo (fase inicial)
- Reescrever em Go.
- Trocar protocolo de metadata (FIFO continua).
- Refatoracao estetica grande de UI.
- Mudancas de hardware/driver.

## Arquitetura Alvo
- Fonte de eventos: shairport-sync metadata FIFO (`/tmp/shairport-sync-metadata`).
- Ingestao: `OceanoClient`.
- Processamento de estado: loop principal + state machine atual.
- Renderizacao: `Renderer` para framebuffer.

Contrato funcional minimo:
- status: `play` ou `stop`
- title, artist, album
- seek, duration
- opcional: `_resolved_artwork`

## Plano por Fases

## Fase 0 - Bootstrap e naming
1. Definir nome final do projeto (ex.: `oceano-now-playing`).
2. Atualizar metadados de pacote:
   - `pyproject.toml`: name, description, keywords, urls.
   - `README.md`: titulo e proposta.
3. Criar branch de trabalho:
   - `fork/oceano-only-bootstrap` (ja criada).

Criterio de pronto:
- Projeto identifica-se como Oceano-focused em pacote e README.

## Fase 1 - Remocao de multi-backend
1. Em `src/app/main.py`:
   - Remover imports de Volumio, Moode e PiCore.
   - Remover `auto_detect_media_player` multi-backend.
   - `detect_media_player` deve retornar somente `OceanoClient`.
2. Em `src/config.py`:
   - `media_player_type` fixo em `oceano` (ou manter campo mas validar apenas `oceano`).
   - Remover URLs de `volumio_url`, `moode_url`, `lms_url`.
   - Manter `oceano_metadata_pipe`.
3. Em `src/media_players/__init__.py`:
   - Exportar somente base + Oceano (ou apenas Oceano, conforme uso).

Criterio de pronto:
- Aplicacao inicia sem ramificacoes de backend e sem referencia a outros players.

## Fase 2 - Limpeza de testes
1. Remover/ajustar testes de Volumio, Moode, PiCore:
   - `tests/test_volumio.py`
   - `tests/test_moode.py`
   - `tests/test_picore_player.py`
   - partes relevantes de `tests/test_media_player.py`
2. Manter e fortalecer:
   - testes de `OceanoClient`
   - testes de state machine
   - testes de renderer
   - testes de config (agora Oceano-only)
3. Garantir cobertura dos casos criticos Oceano:
   - pipe ausente
   - pipe sem atividade
   - bursts de metadata
   - metadata parcial (Unknown) e grace period
   - artwork externo fallback

Criterio de pronto:
- Suite de testes passando no fork sem dependencias dos backends removidos.

## Fase 3 - Documentacao e operacao
1. Atualizar `README.md` com:
   - visao Oceano-only
   - instalacao
   - variaveis de ambiente relevantes
   - troubleshooting de shairport-sync metadata pipe
2. Atualizar scripts (`install.sh`, `setup.sh`, `Makefile`) para refletir escopo.
3. Revisar docs de arquitetura.

Criterio de pronto:
- Onboarding limpo para novo colaborador em 10 minutos.

## Fase 4 - Integracao com oceano-player (Go)
1. Definir contrato operacional entre repos:
   - Caminho FIFO (default e override)
   - Garantias de disponibilidade
   - Ordem de boot (systemd)
2. Publicar recomendacao de unit dependencies:
   - oceano-now-playing depende de shairport-sync ativo
3. Criar guia de deploy conjunto.

Criterio de pronto:
- Usuario instala oceano-player + oceano-now-playing sem ajustes manuais complexos.

## Riscos e mitigacoes
1. Risco: quebrar state transitions ao remover caminhos de auto-detect.
   - Mitigacao: manter testes de estado e transicoes.
2. Risco: regressao em renderizacao por metadata incompleta.
   - Mitigacao: reforcar testes com `Unknown`/campos vazios.
3. Risco: acoplamento fragil com FIFO timing.
   - Mitigacao: validar comportamento com timeout e reconexao.

## Checklist de execucao (ordem sugerida)
1. Atualizar nome e metadata do projeto.
2. Simplificar `main.py` para Oceano-only.
3. Simplificar `config.py` para Oceano-only.
4. Ajustar exports em media_players.
5. Remover/ajustar testes de players antigos.
6. Rodar testes e corrigir regressao.
7. Atualizar README e scripts.
8. Criar PR interno de baseline.

## Definicao de pronto (MVP do fork)
- Projeto roda com `MEDIA_PLAYER=oceano` sem opcoes alternativas.
- Nenhuma referencia ativa a Volumio/Moode/PiCore no runtime.
- Testes relevantes passando.
- README descreve claramente o uso com oceano-player.
