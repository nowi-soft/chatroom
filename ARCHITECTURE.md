# Chatroom — Arquitectura e historia del proyecto

> **Para agentes de IA**: este documento es el punto de entrada para entender qué es este repo, por qué está así, qué falta y cómo continuar. Leelo completo antes de tocar cualquier cosa.

---

## ¿Qué es esto?

Un sistema Odoo (v19, branch `19.0`) que conecta canales externos de mensajería (WhatsApp vía Evolution, Telegram) con:

1. **Operadores humanos** — ven todos los chats en un panel propio (`ChatroomApp`), pueden responder, asignar, tomar notas, vincular a leads/partners/productos.
2. **Agentes de IA** — responden automáticamente a clientes externos usando el framework `muk_ai` (de muk-it), con una base de conocimiento del negocio inyectada en el system prompt.
3. **Un agente creador de agentes** — un asistente de IA interno que guía al dueño de negocio (no técnico) a configurar su propio agente customer-facing, creando los registros de Odoo por él, sin que el dueño tenga que tocar ningún formulario.

El cliente objetivo son **pymes argentinas** (distribuidoras, carnicerías, centros de motos, etc.) que quieren atender WhatsApp automáticamente sin contratar a nadie técnico.

---

## Historia: de dónde venimos

### v18 (branch `master`, legado)

Había un stack de IA artesanal construido encima de chatroom:

- `chatroom_ai` — runtime propio (solo OpenAI, tools vía `exec()`, sin approval gates, sin cost tracking).
- `chatroom_ai_openai` — provider OpenAI propio.
- `chatroom_ai_crm` — tools de CRM propias.
- `queue_job` — async vía cola de jobs.

Problemas: frágil, solo un provider, sin audit, sin approval gates, complejidad alta para mantener.

### Decisión de migración

Al encontrar `muk_ai` (framework de IA de muk-it para Odoo v19), se decidió:

- **Reemplazar el runtime artesanal por `muk_ai` completo** — tiene multi-provider (OpenAI/Anthropic/Google), tools vía `@mcp_tool` decorator, session runtime con cron worker + advisory locks, approval gates, audit log, catálogo de modelos con pricing.
- **Migrar todo a v19** — `muk_ai` solo existe en v19, no vale la pena portarlo.
- **Big-bang** — no hay clientes en producción todavía, así que sin migration scripts ni feature flags.
- **Sin `queue_job`** — muk_ai usa cron worker propio.

Los 3 módulos de IA viejos fueron **borrados** (`30f8a4c`). Lo que sobrevive del v18: el `MANAGEMENT_SYSTEM_PROMPT` del agente creador, portado como data seed XML.

---

## Módulos del repo

### Conservados (migrados a v19)

| Módulo | Qué hace |
|---|---|
| `chatroom` | Core: `chatroom.room`, `chatroom.message`, `chatroom.contact`. La UI `ChatroomApp` (OWL) vive acá. |
| `chatroom_connector` | Base para conectores externos; WebSocket bus, API de outbound. |
| `chatroom_evolution` | Conector Evolution (WhatsApp). Webhook inbound + outbound API. |
| `chatroom_telegram` | Conector Telegram. |
| `chatroom_crm` | Vinculación chatroom ↔ `crm.lead`. No depende de IA. |
| `chatroom_simulator` | Simula mensajes entrantes para testing sin Evolution real. |

### Nuevos (creados en la migración)

| Módulo | Qué hace |
|---|---|
| `muk_ai_knowledge` | KB persistente. Modelo `muk_ai.knowledge` con m2m a `muk_ai.agent`. Inyecta contenido en el system prompt (modo `inline`) o lo expone como tool (modo `tool`). Soporta PDF, DOCX, XLSX, TXT, MD, CSV. |
| `chatroom_ai_bridge` | Adapter entre chatroom y muk_ai. Ver sección completa abajo. |

### Módulos externos requeridos (no en este repo)

Del repo `muk-it/odoo-modules` (branch `19.0`):
- `muk_mcp` — registro de MCP tools (`@mcp_tool` decorator, `get_tool_index`).
- `muk_ai` — runtime de sesiones, agentes, providers, eventos.
- `muk_web_utils` — utilidades web que muk_ai necesita.

---

## Arquitectura de la IA

### Flujo customer-facing (WhatsApp → Odoo → respuesta)

```
WhatsApp
  → Evolution webhook
    → chatroom_evolution (crea chatroom.message direction=incoming)
      → chatroom.message.create hook (chatroom_ai_bridge)
        → chatroom.room._ensure_ai_session() → crea/recupera muk_ai.session
          → session.send_message(body)
            → muk_ai cron worker procesa
              → LLM responde
                → muk_ai.session._append_event(kind='text') hook (chatroom_ai_bridge)
                  → crea chatroom.message direction=outgoing
                    → chatroom_connector envía a Evolution
                      → WhatsApp
```

### Flujo agente creador (interno, dueño del negocio)

El agente creador vive en `/odoo/ai` (chat UI nativa de muk_ai). El dueño abre esa pantalla, selecciona el agente "AI Configuration Assistant" y conversa. El agente crea los registros de Odoo usando las tools genéricas de muk_mcp (`create_records`, `update_records`, etc.).

**No hay código custom para el agente creador** — es puramente data seed (`data/agent_creator.xml`) con un system prompt muy trabajado.

---

## `chatroom_ai_bridge` — detalles

### Campos agregados a `chatroom.room`

- `muk_ai_agent_id` (Many2one → `muk_ai.agent`) — qué agente responde en este room. Vacío = sin auto-respuesta.
- `muk_ai_session_id` (Many2one → `muk_ai.session`) — sesión activa para este room.

### Punto de entrada inbound

`chatroom_message.py` — hook en `create`. Si el mensaje es `direction=incoming` y el room tiene `muk_ai_agent_id`, delega a `_ensure_ai_session()` + `session.send_message()`.

### Punto de salida outbound

`muk_ai_session.py` — override de `_append_event`. Cuando `kind='text'`, resuelve el room asociado y crea el `chatroom.message outgoing`.

### Agentes customer-facing (`muk_ai_agent.py`)

Extiende `muk_ai.agent` con:
- `is_customer_facing` (Boolean) — activa el template estándar.
- `agent_tone` (Char) — idioma y tono (ej: "español rioplatense, amigable, de vos").

Cuando `is_customer_facing=True`, `_build_system_prompt()` reemplaza el `system_prompt` del agente por `CUSTOMER_FACING_TEMPLATE` (hardcodeado en el modelo). Esto evita que el agente creador escriba prompts verbosos/restrictivos que hacen que el agente rechace contestar preguntas cubiertas por la KB.

**Decisión importante**: `apply_tool_filter` NO está sobreescrito para agentes customer-facing. Intentamos restringir las tools a solo `['ask_user']` pero gpt-5.4 alucinaba JSON de tool-calls como texto plano. El compromiso actual: `_get_essential_tool_names` retorna `['ask_user']` (no anuncia tools de Odoo de forma eager), pero el modelo puede lazy-cargar otras si el LLM las pide.

### Bot user dedicado

`data/chatroom_user_bot.xml` — crea un `res.users` de sistema (`chatroom_bot`) que es el `user_id` de todas las sesiones customer-facing. Necesita `partner_id` válido para que muk_ai no rompa en el bus listener.

---

## `muk_ai_knowledge` — detalles

### Modelo `muk_ai.knowledge`

Campos clave: `name`, `content_type` (text/html/file), `content`, `file` (binary), `processed_content` (texto limpio listo para LLM), `processing_status`, `char_count`, `agent_ids` (m2m a `muk_ai.agent`).

### Inyección en system prompt

`models/ai_agent.py` extiende `muk_ai.agent` con m2m `knowledge_ids` y `kb_mode`. En `_build_system_prompt()`, si `kb_mode='inline'`, concatena todo el contenido procesado de las KBs debajo del system prompt con el header `=== KNOWLEDGE BASE ===`.

### Tool `create_knowledge_from_attachment`

`models/mcp_tools.py` — tool `@mcp_tool` que el agente creador puede llamar cuando el dueño le manda un PDF/Excel. Recibe `attachment_id`, extrae texto, crea el registro `muk_ai.knowledge` y opcionalmente lo vincula a un agente.

### Extracción de texto

`utils/text_extraction.py` — soporta `.txt`, `.md`, `.csv`, `.pdf` (PyPDF2), `.docx` (python-docx), `.xls`/`.xlsx` (pandas+openpyxl).

---

## Decisiones de diseño tomadas (no reabrir sin buena razón)

| Decisión | Razonamiento |
|---|---|
| **Mantener `ChatroomApp`** como UI del operador | Resuelve un problema distinto a la chat UI de muk_ai. `ChatroomApp` = panel multi-room para operadores humanos. muk_ai chat = ventana 1:1 estilo ChatGPT para admin interno. |
| **Agente creador en `/odoo/ai`** (no dentro de ChatroomApp) | Elimina toda la complejidad del "AI Setup room" del v18. El data seed ya aparece en el agent picker de muk_ai sin más trabajo. |
| **`is_customer_facing` + template hardcodeado** | El agente creador (LLM) invariablemente genera system prompts verbosos con muchos "si falta info derivá a humano" que hacen que el agente rechace contestar preguntas cubiertas por la KB. El template fijo, probado y refinado, resuelve esto sin depender de la calidad del output del LLM. |
| **Sin `queue_job`** | muk_ai resuelve el async con cron worker + advisory locks. |
| **KB inline por defecto** (no vector store) | Para pymes con catálogos chicos (< 50k chars), inline en el context window es suficiente. YAGNI. |
| **Bot user con `sudo()` para todas las ops** | El bot user tiene permisos mínimos, pero todas las ops del bridge usan `.sudo()` para poder crear mensajes/sesiones en cualquier contexto. |

---

## Problemas conocidos y abiertos

### GPT en "modo Odoo" — diagnóstico completo post-prueba end-to-end (2026-06-07)

Se corrió una prueba completa con **gpt-4.1** (OpenAI) contra "Asistente Motorepuestos La Cadena". Resultados:

**Lo que funciona con GPT-4.1:**
- `invoke_skill` se llama correctamente en la mayoría de los casos (horarios, precios, envíos, pedido grande con precio de lista).
- `escalate_to_human` funciona perfectamente ante reclamos.
- El bug de `search_read` / `read_records` (`_essential_tool_names = ['ask_user', 'invoke_skill', ...]`) **NO apareció** con gpt-4.1 — solo con gpt-5.4.

**Problemas residuales con GPT-4.1 (no solucionables con template):**

1. **Alucinación de URLs de Odoo**: el modelo genera links a `odoo.com/documentation/...` aunque el system prompt lo prohíbe explícitamente. Es un prior de entrenamiento más fuerte que el system prompt.

2. **Regla de rubro ignorada**: ante "tenés repuestos para autos Ford?" el modelo ofrece buscar en el catálogo en vez de decir "solo trabajamos con motos". La regla está en el template pero GPT-4.1 prioriza su "helpfulness" por encima de las restricciones de scope.

3. **Captura de datos en pedido grande**: el modelo da el precio de lista para 20 kits en vez de pedir nombre+teléfono+zona antes. La regla está en el template pero no se aplica.

**Lo que probamos en el template** (sin resolver los 3 puntos):
- Primer intento: agregar guía de `invoke_skill` por topic + regla FUERA DEL RUBRO + pedir datos "5 unidades o más".
- Segundo intento: reestructurar el template con "REGLAS ABSOLUTAS" numeradas arriba del todo, con ASCII separators, instrucción explícita "No incluyas URLs" y "No intentes buscar fuera del rubro". El modelo sigue ignorándolas.

**Conclusión definitiva**: GPT-4.1 no respeta instrucciones prohibitivas fuertes cuando su prior de entrenamiento es contrario. El template mejorado queda en el repo y es correcto para Claude.

**Fix**: cambiar el `model_id` del agente customer-facing a `muk_ai.model_claude_sonnet_4_5` (Anthropic) y configurar `muk_ai.provider_anthropic` con una API key. Es un cambio de configuración, no de código. La arquitectura ya soporta multi-provider.

### Agente creador y `is_customer_facing`

**Síntoma**: el LLM del agente creador a veces ignora la instrucción "no escribas system_prompt, setea `is_customer_facing=True`" y escribe un system_prompt propio.

**Estado**: el system prompt del agente creador tiene instrucciones explícitas y el ejemplo muestra el campo vacío. Funciona en la mayoría de los casos pero no siempre.

**Fix posible**: agregar validación server-side que borre `system_prompt` si `is_customer_facing=True`.

### Verificación en browser (parcialmente hecha)

El JS bundle compila OK (1264 archivos, 4 de chatroom, sin errores). El servidor Odoo v19 responde en `http://localhost:18069`. Falta abrir el menu Chatroom en un browser real y verificar que no hay errores OWL en la consola.

---

## Entorno de desarrollo

### Ubicación

`/Users/francoleyes/nowi/19/` — espejo de la estructura de `/Users/francoleyes/nowi/18/` (convención: carpeta = versión de Odoo).

### Puertos

- `127.0.0.1:18069:8069` — Odoo web
- `127.0.0.1:18072:8072` — Odoo bus/websocket
- `127.0.0.1:8089:8081` — pgweb

### Variables clave

- `COMPOSE_PROJECT_NAME=nowi19` — evita colisión de nombres con el proyecto adhoc "19" que corre en paralelo.
- `ODOO_VERSION=19`

### Levantar Odoo

```bash
cd /Users/francoleyes/nowi/19
docker compose up -d
docker exec -it 19-odoo bash
# dentro del container:
odoo --database migrate_test --stop-after-init --no-http  # para init/update
odoo --database migrate_test  # para servidor web
```

### Instalar los módulos

En el container, con Odoo corriendo:
```
Ajustes > Activar modo desarrollador > Módulos > instalar:
  muk_ai_knowledge
  chatroom_ai_bridge
  (esto arrastra muk_ai, muk_mcp, chatroom, chatroom_connector, etc.)
```

### Provider de IA

Configurar en Ajustes > muk_ai > Providers. Se necesita API key de OpenAI/Anthropic/Google. Para development, OpenAI con `gpt-4o` funciona. Para producción con agentes customer-facing, Claude (`claude-sonnet-4-x`) es preferible (ver problema conocido arriba).

---

## Pendientes priorizados

### Must-have antes de primer piloto con cliente

1. **Fix modelo para agentes customer-facing** ⚠️ URGENTE — cambiar `model_id` del agente a `muk_ai.model_claude_sonnet_4_5` y configurar `muk_ai.provider_anthropic` con API key de Anthropic. GPT-4.1 ignora reglas de scope y genera URLs alucinadas de Odoo; confirmado en prueba end-to-end del 2026-06-07. El template está listo para Claude.

2. **Verificación browser real** — abrir ChatroomApp en browser, confirmar que levanta sin errores OWL, que los rooms se listan y que se puede responder manualmente.

3. **Evolution sandbox real** — probar WhatsApp inbound/outbound con un número real (no solo scripts Python). El webhook de Evolution está configurado en `chatroom_evolution`; falta un número de prueba.

### Nice-to-have

4. **Demo data declarativo** — `chatroom_ai_bridge/demo/fictional_business.xml` con "Distribuidora La Norteña" (agente + KBs preconfigurados). Hoy los scripts de prueba viven en `/tmp/` y se pierden al reiniciar el container.

5. **`agent_creator_test_script.md`** — guión de la conversación con el agente creador para que los tests sean reproducibles sin inventar datos cada vez.

6. **Reusar componentes muk_ai en ChatroomApp** — reemplazar el rendering de attachments en `chatroom/static/src/components/chatroom_app/chatroom_app.xml:316-368` por `<AttachmentCard />` de muk_ai, y pasar el body de mensaje por `renderMarkdown()`.

7. **Validación server-side de `is_customer_facing`** — si `is_customer_facing=True` y `system_prompt != ''`, logear warning o borrarlo para que el template se aplique siempre.

8. **Push del entorno v19** — el commit `1e42ed8` en `/Users/francoleyes/nowi/19/` no tiene upstream. Decidir si va a `main` de `nowi-soft/odoo-docker-dev` o a una branch `v19-env`.

9. **Concurrencia entre rooms** — con muchos rooms simultáneos el cron worker de muk_ai puede saturarse. No medido todavía. Si la latencia es > 5s consistente, evaluar dispatch inline desde el webhook.

10. **`search_knowledge` tool** — para `kb_mode='tool'` cuando la KB total excede el context window. YAGNI para pymes, pero útil para negocios con catálogos grandes.

---

## Archivos clave para entender el sistema

| Archivo | Por qué leerlo |
|---|---|
| `chatroom_ai_bridge/models/chatroom_room.py` | `_ensure_ai_session()` — cómo se conecta un room a una session de muk_ai |
| `chatroom_ai_bridge/models/chatroom_message.py` | Hook inbound — cómo un mensaje incoming dispara el agente |
| `chatroom_ai_bridge/models/muk_ai_session.py` | Hook outbound — cómo el texto del LLM se convierte en chatroom.message |
| `chatroom_ai_bridge/models/muk_ai_agent.py` | Template customer-facing + `is_customer_facing` + por qué NO se sobreescribe `apply_tool_filter` |
| `chatroom_ai_bridge/data/agent_creator.xml` | System prompt completo del agente creador |
| `muk_ai_knowledge/models/ai_knowledge.py` | Modelo KB — extracción, procesamiento, vinculación a agentes |
| `muk_ai_knowledge/models/ai_agent.py` | Cómo se inyecta la KB en el system prompt (`_build_system_prompt` override) |
| `muk_ai_knowledge/models/mcp_tools.py` | Tool `create_knowledge_from_attachment` |
| `muk_ai_knowledge/utils/text_extraction.py` | Extracción de texto de PDF/DOCX/XLSX/etc |

### Módulos externos clave (repo muk-it/odoo-modules, branch 19.0)

| Archivo | Por qué leerlo |
|---|---|
| `muk_ai/models/session.py` | Runtime principal — `send_message`, `_run_to_completion`, `_append_event`, `_dispatch_tool_call` |
| `muk_ai/models/agent.py` | `muk_ai.agent` — `_build_system_prompt`, `_get_essential_tool_names`, `apply_tool_filter` |
| `muk_mcp/core/tool.py` | `@mcp_tool` decorator, `get_tool_index` |
