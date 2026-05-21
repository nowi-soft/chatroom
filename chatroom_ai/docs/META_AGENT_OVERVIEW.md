# Meta-agente de chatroom_ai — resumen para Claude

Pegá este archivo en una nueva sesión de Claude Code cuando vuelvas a trabajar sobre este módulo, así no tenés que reexplicar todo desde cero.

## Qué es

Producto: agente IA para Odoo 18 vendido masivamente a negocios **no técnicos** (motoshops, fiambrerías, colchones, etc.). El agente final responde clientes por WhatsApp/Telegram y crea leads en Odoo cuando hay intención de compra.

Para que el cliente final pueda configurar su propio agente **sin ayuda técnica**, existe un **meta-agente**: un chat dentro de Odoo donde el manager conversa con un "AI Configuration Assistant" que crea/actualiza el agente final, sus knowledge bases y sus tools usando function calling de OpenAI.

## Stack

- **Odoo 18.0** (`/Users/francoleyes/nowi/18/versions/18/repositories/chatroom`)
- **Módulos:** `chatroom`, `chatroom_ai`, `chatroom_ai_openai`, `chatroom_ai_crm`, `chatroom_connector`, `chatroom_evolution`, `chatroom_telegram`, `chatroom_simulator`
- **OpenAI** function calling clásico (NO MCP). Provider con abstracción `chatroom.ai.provider` + adapter en `chatroom_ai_openai`.
- **Queue jobs** (`queue_job` de OCA) para procesar mensajes async.
- **Frontend OWL** en `chatroom/static/src/components/chatroom_app/` reutilizado para el management room vía patch en `chatroom_ai/static/src/chatroom_app_ai_patch.js`.

## Arquitectura del meta-agente

| Cosa | Dónde |
|---|---|
| System prompt + lista de tools | `chatroom_ai/models/chatroom_ai_management.py` (`MANAGEMENT_SYSTEM_PROMPT`, `MANAGEMENT_TOOLS`) |
| Tools (14 en total) | `chatroom_ai/data/chatroom_ai_management_tools_data.xml` |
| Auto-setup del agente + room al activar el provider | `_ensure_management_setup()` en el mismo `chatroom_ai_management.py` (corre desde `action_test_connection` + `post_init_hook` + `data/chatroom_ai_management_setup.xml` en update) |
| Modelo de room con flag | `chatroom.room.is_management_room` en `chatroom_ai/models/chatroom_room.py` |
| Modelo de agent con flag | `chatroom.ai.agent.is_management_agent` en `chatroom_ai/models/chatroom_ai_agent.py` |
| Loop de tool calls (cap 20) | `_generate_and_send_response()` en `chatroom_ai_agent.py` (constante `MAX_TOOL_ITERATIONS`) |
| Procesamiento async de mensajes | `_job_process_room_messages()` en `chatroom_ai/models/chatroom_message.py` |
| Front: botón "AI Setup" y gating de provider | `chatroom_ai/static/src/chatroom_app_ai_patch.js` (`setup` → `onMounted`) |
| Helper unificado de extracción de texto (PDF/DOCX/XLS/TXT/MD/CSV) | `chatroom_ai/utils/text_extraction.py` |

## Flujo "manager configura su agente"

```
1. Admin crea AI Provider OpenAI con API key → "Test Connection"
   ↓ action_test_connection → state='active' → _ensure_management_setup()
2. Se crea management agent + management room (idempotente)
3. Manager (grupo chatroom_manager) abre /chatroom
   ↓ patch.js#onMounted verifica provider activo → setea state.managementRoom
4. Click "AI Setup" → openManagementRoom() → carga el chat
5. Manager escribe → chatroom.message create (incoming, user_id=session.uid)
   ↓ queue_job _job_process_room_messages (delay 15s para batch)
6. Job arma messages = room.build_context_messages() (system prompt + KBs + contexto)
   ↓ provider.generate_completion(messages, tools=14 management tools)
7. Loop:
   - Si tool_calls → ejecutar c/u → reinyectar → re-llamar
   - Si content → crear chatroom.message outgoing (is_ai_generated=True)
   - Cap 20 iteraciones
```

## Flujo "manager adjunta PDF → va a KB del agente final"

```
1. Manager drag-drops PDF al management room
   ↓ patch.js#uploadFile (rama is_management) → /chatroom/upload_file → ir.attachment
   ↓ create chatroom.message (attachment_id, body="", user_id=session.uid)
2. Job _job_process_room_messages rama is_management
   ↓ helper extract_text_from_attachment(att) → char_count
   ↓ room.add_text_to_context("[Attachment received: ..., message_id=N, ~Nchars]")
   ↓ NO mete el contenido completo (eso se pierde con max_conversation_length)
3. Meta-agente "ve" la referencia
   ↓ pregunta al manager "¿a qué agente lo agrego, con qué nombre?"
4. Manager confirma
   ↓ meta-agente llama tool create_knowledge_from_attachment(message_id, name, agent_id?)
   ↓ tool re-extrae texto, crea chatroom.ai.knowledge (content_type='file',
     file=att.datas, processed_content=<extraído>, processing_status='success')
   ↓ si agent_id viene: M2M con el agente
5. La KB ya está persistida; al responder, el agente final inyecta el texto en
   su system prompt vía get_formatted_content().
```

## Comandos de entorno

Desde `/Users/francoleyes/nowi/18`:

```bash
# .env debe tener ODOO_VERSION=18
docker compose up -d                 # arranca odoo, db, pgweb, smtp, dns
# (el container 'odoo' corre `sleep infinity`; hay que disparar Odoo a mano)

# Primera vez: instalar el módulo
docker compose exec odoo odoo -d test -i chatroom_ai --stop-after-init

# Iteración: actualizar el módulo
docker compose exec odoo odoo -d test -u chatroom_ai --stop-after-init

# Para correr Odoo en modo dev en foreground (útil para tail de logs):
docker compose exec odoo odoo -d test --dev=xml,reload

# URLs locales:
#   Odoo:    http://18.odoo.localhost     (requiere profile local-traefik OR /etc/hosts)
#   pgweb:   http://127.0.0.1:8081
#   mailpit: http://127.0.0.1:8025
```

Si no querés Traefik, podés hacer `docker compose exec odoo odoo ...` y mapear puerto 8069. O usar el profile `local-traefik` y editar `/etc/hosts` con `127.0.0.1 18.odoo.localhost` (o usar el DNS contenedor).

## Gotchas / cosas a recordar

- **`noupdate="1"`** en los XML de tools de management: las tools nuevas se crean en update; las existentes NO se modifican. Si cambiás `python_code` de una tool existente, hay que borrarla manualmente del DB o renombrar el XML id.
- **Re-sync del management agent en update**: lo dispara `data/chatroom_ai_management_setup.xml` (function call a `_ensure_management_setup`). Sin esto, las tools nuevas no se asignan al management agent en `-u`.
- **Contexto efímero del agente**: `chatroom.ai.agent.max_conversation_length` (default 20) trimea el contexto. Por eso los attachments se referencian en lugar de pegar contenido completo.
- **El management agent no aparece en el sidebar regular**: `chatroom_app.js` filtra por `is_management_room != true`. Verificar siempre que un cambio no rompa este filtro.
- **Identidad en management room**: los mensajes del manager se crean con `user_id = session.uid` (no sólo `author_name` libre). Si no hay sesión, queda `null` y se usa el `author_name`.
- **Provider inactivo**: el patch JS chequea `searchCount(chatroom.ai.provider, [state='active'])` antes de mostrar el botón "AI Setup". Si está inactivo, el botón no aparece.
- **Loop de tool calls** está cappeado en 20 iteraciones (`MAX_TOOL_ITERATIONS`). Si un agente queda loopeando con tools, corta y se loguea un warning.
- **Multimedia no soportada** en rooms regulares (no management): si el agente recibe un archivo/imagen, responde con `agent.unsupported_media_message`. En management room, en cambio, los archivos soportados (PDF/DOCX/XLS/TXT/MD/CSV) inyectan una referencia que el meta-agente puede usar.

## Lo que NO está implementado y por qué

- **Topics para agrupar tools** (estilo Odoo v19 enterprise): 14 tools planas son manejables; no aporta valor a corto plazo.
- **Multimodal directo al LLM** (imágenes/PDF al endpoint multimodal de OpenAI sin pre-extraer texto): fuera de scope. Hoy todo va por extracción de texto.
- **RAG con embeddings**: las KBs se inyectan como texto plano al system prompt. Funciona para KBs chicas/medianas. Para KBs grandes habría que migrar a embeddings + retrieval.
- **MCP**: descartado. Odoo enterprise v19 tampoco usa MCP; usan function calling clásico.

## Fixture de prueba

`chatroom_ai/tests/fixtures/sample_business_motoshop.md` tiene el guion completo de 10 turnos para probar el meta-agente con datos de una tienda de motos ficticia "MotoSur", incluyendo:

- Datos del negocio (productos, precios, FAQs, horarios).
- 10 turnos copy-paste en orden.
- Catálogo PDF en `sample_business_motoshop_catalog.pdf` para probar el flujo de adjuntos→KB.
- Queries SQL de verificación.
- Cómo probar el agente final una vez creado.

Para regenerar el PDF (si editás el catálogo en el `.md`):

```bash
pip install reportlab
python chatroom_ai/tests/fixtures/generate_catalog_pdf.py
```

## Recordatorio de memoria

Hay una entrada en `~/.claude/projects/-Users-francoleyes-nowi-18/memory/project_chatroom_ai.md` con la arquitectura general. **Mantenerla actualizada** cuando cambien decisiones grandes (ej. si en algún momento se migra a Discuss, a embeddings, o se agregan topics).
