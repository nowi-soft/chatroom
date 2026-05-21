# MotoSur — Fixture de prueba para el meta-agente

Datos de una empresa ficticia para probar el flujo completo del meta-agente
(crear agente + agregar KB desde texto + agregar KB desde adjunto + asignar tools).

Copy-paste los turnos en orden cuando estés probando en la "AI Setup" room.
Antes de empezar: asegurate de tener un AI Provider OpenAI en estado **active**.

---

## Datos del negocio

- **Nombre:** MotoSur
- **Rubro:** Tienda de motos y repuestos
- **Ubicación:** Av. Colón 2300, Córdoba Capital, Argentina
- **Horarios:** Lunes a Viernes 9-13 / 16-20, Sábados 9-13
- **Teléfono:** +54 351 555-1234
- **Web:** motosur.com.ar

## Productos destacados (extracto del catálogo)

| Producto | Precio |
|---|---|
| Honda Wave 110 0km | $1.350.000 |
| Yamaha YBR 125 0km | $1.890.000 |
| Honda CB 190R 0km | $3.250.000 |
| Bajaj Rouser 220F 0km | $2.480.000 |
| Casco Hawk RS5 negro talle M | $85.000 |
| Casco Hawk integral RS9 talle L | $145.000 |
| Cubierta Pirelli 110/80-17 | $42.000 |
| Cubierta Pirelli 130/70-17 | $58.000 |
| Aceite Motul 5100 4T 1L | $14.500 |
| Aceite Motul 7100 4T 1L | $22.000 |
| Kit transmisión Honda Wave (corona + piñón + cadena) | $38.000 |
| Batería YTX9-BS Yuasa | $48.000 |
| Guantes Alpinestars SP-1 | $55.000 |
| Campera Alpinestars Vento Air | $185.000 |
| Service básico Honda Wave (mano de obra) | $25.000 |

## FAQs

- **¿Aceptan tarjeta?** Sí, Visa y Mastercard hasta 12 cuotas sin interés con bancos seleccionados.
- **¿Hacen envíos al interior?** Sí, despachamos por Andreani a todo el país. El costo se calcula
  al cierre del pedido y queda a cargo del cliente.
- **¿Patentan la moto?** Sí, gestionamos el patentamiento para motos 0km financiadas
  (sin costo extra) o no financiadas (cargo de gestoría $80.000).
- **¿Tienen garantía?** Las motos 0km tienen garantía oficial del fabricante
  (12 meses o 12.000 km). Repuestos originales 6 meses; aftermarket 30 días.
- **¿Hacen service?** Sí, taller propio. Service básico desde $25.000.
  Reservar turno por WhatsApp.
- **¿Tienen financiación?** Sí. Plan Mi Moto del Gobierno hasta 48 cuotas para 0km
  seleccionadas. Tarjeta de crédito hasta 12 cuotas.
- **¿Aceptan permuta de moto usada?** Sí, tasamos en el local con turno previo.

---

## Guion de conversación con el meta-agente

> Pegá un turno por vez, esperá la respuesta del meta-agente y respondé el siguiente.
> El meta-agente debería ir haciendo preguntas para refinar; si avanza demasiado rápido,
> aclará "una sola pregunta a la vez".

### Turno 1 — saludo

```
Hola, quiero configurar el agente IA para mi tienda de motos.
```

### Turno 2 — qué hace el negocio

```
Vendemos motos 0km y usadas, repuestos originales y accesorios.
También hacemos service en nuestro taller. Estamos en Córdoba Capital.
```

### Turno 3 — qué preguntan los clientes

```
Los clientes preguntan precios de motos, si tenemos un modelo en stock,
si financiamos, qué cuotas hay, costos de envío al interior y horarios.
También consultan por repuestos puntuales y por turnos de service.
```

### Turno 4 — captura de leads

```
Cuando alguien pregunte por una moto específica o quiera saber financiación,
quiero que el agente capture su nombre, teléfono y el modelo que le interesa
como lead en Odoo, antes de dar el precio final.
```

### Turno 5 — tono

```
Tono amigable pero profesional. Que hable de vos (no de usted).
En castellano rioplatense.
```

### Turno 6 — KB desde texto

```
Quiero también que sepa los horarios y la dirección. Horario: lunes a viernes
9 a 13 y 16 a 20, sábados 9 a 13. Dirección: Av. Colón 2300, Córdoba.
Teléfono +54 351 555-1234.
```

> El meta-agente debería llamar a `create_knowledge` con esa info y luego
> `associate_knowledge_to_agent`.

### Turno 7 — adjuntar el catálogo PDF

> Arrastrá `sample_business_motoshop_catalog.pdf` al chat (o usá el botón de adjuntar).

```
Acabo de subirte el catálogo de productos con precios. Por favor agregalo
como base de conocimiento del agente, llamala "Catálogo MotoSur".
```

> Esperado: el meta-agente reconoce el `[Attachment received: ...]`, pregunta a qué agente,
> y al confirmar llama `create_knowledge_from_attachment`.
> Verificá que `processing_status='success'` y que `char_count > 0`.

### Turno 8 — asignar tool de leads

```
Asignale al agente la tool de crear leads.
```

> Esperado: llamadas en cadena `list_available_tools` → `assign_tools_to_agent`.
> Si tu loop de tool calls está bien, esto se hace en un solo turno del usuario.

### Turno 9 — verificación

```
Mostrame los detalles del agente que creaste: nombre, system prompt resumido,
qué KBs tiene y qué tools.
```

> Esperado: llamada `get_agent_details`.

### Turno 10 — cierre

```
Perfecto, eso es todo. Gracias.
```

---

## Verificación post-conversación

Después de los 10 turnos, en pgweb (o psql) ejecutá:

```sql
-- Debería haber 2 agentes: el management y el de MotoSur
SELECT id, name, is_management_agent, provider_id IS NOT NULL AS has_provider,
       LENGTH(system_prompt) AS prompt_len
FROM chatroom_ai_agent
ORDER BY id;

-- Debería haber 2 KBs: una de texto (horarios/dirección) y una de archivo (catálogo)
SELECT id, name, content_type, processing_status, char_count, file_name
FROM chatroom_ai_knowledge
ORDER BY id;

-- M2M: las 2 KBs deberían estar asociadas al agente de MotoSur
SELECT agent.name AS agent, kb.name AS kb
FROM chatroom_ai_agent_knowledge_rel rel
JOIN chatroom_ai_agent agent ON agent.id = rel.agent_id
JOIN chatroom_ai_knowledge kb ON kb.id = rel.knowledge_id
WHERE NOT agent.is_management_agent;

-- El agente debería tener la tool create_lead (al menos)
SELECT agent.name, tool.code_name
FROM chatroom_ai_agent_tool_rel rel
JOIN chatroom_ai_agent agent ON agent.id = rel.agent_id
JOIN chatroom_ai_tool tool ON tool.id = rel.tool_id
WHERE NOT agent.is_management_agent;
```

## Prueba del agente final

1. Creá una room nueva (no management): `Chatroom → New Room`.
2. Asignale el agente "Asistente de MotoSur" (o como lo haya bautizado el meta-agente).
3. Habilitá AI Enabled.
4. Como visitante, mandá: "Hola, cuánto sale la Honda Wave?"
5. Esperado: el agente responde con el precio del catálogo ($1.350.000) y eventualmente
   pide tus datos para registrar el interés como lead.
