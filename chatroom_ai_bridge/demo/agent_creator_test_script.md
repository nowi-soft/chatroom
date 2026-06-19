# Script de test: Agente creador — "Distribuidora La Norteña"

**Propósito**: guión reproducible para testear el flujo completo del "AI Configuration
Assistant" (agente creador) desde cero. Seguí este script en orden para crear un agente
customer-facing funcional sin inventar datos en el momento.

**Prerequisitos**:

- Módulos instalados: `chatroom_ai_bridge`, `muk_ai_knowledge`
- Provider OpenAI o Anthropic configurado en Ajustes → AI Providers
- Abrí `/odoo/ai` en el browser y seleccioná **AI Configuration Assistant** como agente

---

## Parte 1: Conversación con el agente creador

> Las líneas marcadas como **[VOS]** son lo que escribís en el chat. Las líneas
> **[AGENTE]** son lo que debería responder (aproximado — el LLM varía). Las líneas
> **[VALIDAR]** son checks intermedios que podés hacer.

---

### Turno 1 — Inicio

**[VOS]**

```
hola, quiero que me ayudes a crear un agente para mi distribuidora
```

**[AGENTE]** _(debería preguntar el nombre/tipo de negocio)_

```
¡Hola! Con gusto te ayudo a crear tu asistente. Primero, ¿cómo se llama tu negocio y qué tipo de distribuidora es?
```

---

### Turno 2 — Identidad del negocio

**[VOS]**

```
se llama Distribuidora La Norteña, vendemos fiambres y quesos al por mayor, estamos en Córdoba capital
```

**[AGENTE]** _(debería confirmar y preguntar por productos/precios)_

```
Perfecto, anotado: Distribuidora La Norteña, fiambres y quesos mayoristas en Córdoba.
¿Cuáles son los productos que más te preguntan y sus precios aproximados?
```

---

### Turno 3 — Productos y precios

**[VOS]**

```
jamón cocido tipo A $8200 el kilo, jamón crudo horma entera $10800 el kilo,
queso sardo $8600, queso mar del plata $5200, mozzarella en bloque $4800.
pedido mínimo $45000 sin iva
```

**[AGENTE]** _(debería anotar y preguntar sobre consultas frecuentes o logística)_

---

### Turno 4 — Preguntas frecuentes

**[VOS]**

```
nos preguntan mucho sobre si hacemos entregas a otras provincias, los horarios de atención,
y si aceptamos tarjeta de crédito
```

**[AGENTE]** _(debería preguntar por esas respuestas: horarios, zonas, medios de pago)_

---

### Turno 5 — Logística y contacto

**[VOS]**

```
atendemos lunes a viernes de 8 a 17, sábados de 8 a 13.
Enviamos a todo córdoba, a rosario, buenos aires y mendoza con flete del cliente.
No aceptamos tarjeta, solo efectivo o transferencia. Efectivo tiene 5% de descuento.
Pedidos con 24hs de anticipación mínima.
```

---

### Turno 6 — Tono y escala

**[VOS]**

```
el tono que queremos es amigable, de vos, en español rioplatense.
cuando alguien pide una cotización grande, que pida nombre y teléfono y avisamos nosotros
```

---

### Turno 7 — Cierre y creación

**[VOS]**

```
listo, podés crear el agente con todo eso
```

**[AGENTE]** _(debería llamar a `create_records` para crear el `muk_ai.agent` y luego
crear KBs con `create_records` o `create_knowledge_from_attachment`)_

---

## Parte 2: Validación post-creación

Después de que el agente creador diga que terminó, validar en Ajustes → AI Agents:

### Check 1: El agente existe

```sql
-- Desde pgweb o psql:
SELECT name, is_customer_facing, agent_tone, kb_mode
FROM muk_ai_agent
WHERE name ILIKE '%norteña%' OR name ILIKE '%nortena%';
```

**Esperado**: 1 row, `is_customer_facing = true`, `kb_mode = inline`

### Check 2: Las KBs están linkeadas

```sql
SELECT k.name, k.processing_status, k.char_count
FROM muk_ai_knowledge k
JOIN muk_ai_agent_knowledge_rel r ON r.knowledge_id = k.id
JOIN muk_ai_agent a ON a.id = r.agent_id
WHERE a.name ILIKE '%norteña%' OR a.name ILIKE '%nortena%';
```

**Esperado**: al menos 2-3 rows, `processing_status = success`, `char_count > 0`

### Check 3: El agente responde usando la KB

Crear una sesión de prueba en `/odoo/ai` con el agente recién creado y preguntarle:

1. **"¿cuánto sale el jamón crudo?"** → debe responder con el precio ($10.800/kg), sin
   decir "no tengo esa info"
2. **"¿hacen entregas a Mendoza?"** → debe responder que sí, con flete del cliente
3. **"¿hasta qué hora atienden?"** → debe dar el horario correcto
4. **"quiero hacer un pedido grande de quesos"** → debe pedir nombre, teléfono y zona

**Red flags** (si pasa alguno, hay un problema):

- El agente dice "no tengo esa información en el sistema"
- El agente menciona "Odoo", "base de datos", "módulos", "el sistema"
- El agente llama tools de tipo `search_read` o `read_records` en lugar de usar la KB

---

## Parte 3: Test del bridge (respuesta automática)

### Setup

1. Ir a **Chatroom → Rooms**
2. Abrir (o crear) un room
3. Asignar el campo **AI Agent** → seleccionar el agente recién creado (La Norteña)
4. Guardar

### Test

Usando el **chatroom_simulator** (si está instalado):

```
# Simular mensaje entrante
curl -X POST http://localhost:8069/chatroom/simulator/send \
  -H 'Content-Type: application/json' \
  -d '{"room_id": <ID_DEL_ROOM>, "body": "cuanto sale el jamon crudo?"}'
```

**Esperado en el room**: aparece un mensaje outgoing con el precio del jamón.

---

## Parte 4: Test de `create_knowledge_from_attachment` (opcional)

Si querés testear el flujo con archivos:

1. En `/odoo/ai` con el **AI Configuration Assistant**
2. Subir un archivo `.txt` o `.pdf` con información del negocio
3. El agente debería llamar automáticamente a la tool
   `create_knowledge_from_attachment(attachment_id=<id>, name="Catálogo La Norteña")`
4. Verificar en **AI Knowledge** que el registro fue creado con
   `processing_status = success`

---

## Notas de depuración

### Si el agente escribe un `system_prompt` largo (en vez de dejarlo vacío)

El system prompt del agente creador tiene instrucciones explícitas de NO escribir
`system_prompt`. Si lo hace igual:

- Borrar el `system_prompt` manualmente en el registro
- El template `CUSTOMER_FACING_TEMPLATE` se aplica automáticamente cuando
  `is_customer_facing=True` y `system_prompt` está vacío (o en blanco)

### Si el agente responde "no tengo esa información"

Problema: el LLM no está usando la KB. Posibles causas:

1. El provider es `gpt-5.4` (conocido por entrar en "modo desarrollador de Odoo") →
   cambiar a Claude o Gemini
2. Las KBs no tienen `processing_status = success` → reprocessar desde el registro
3. El `kb_mode` es `tool` en vez de `inline` → cambiarlo a `inline`

### Si no aparece respuesta outgoing en el room

Verificar que el cron worker de muk_ai está corriendo:

```
# Desde odoo shell:
env['muk_ai.session'].search([('state','=','running')], limit=5)
env.ref('muk_ai.cron_session_runner').sudo().method_direct_trigger()
```
