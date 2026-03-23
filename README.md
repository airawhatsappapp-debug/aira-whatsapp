# Aira Beta

Aira es una beta de asistente para WhatsApp enfocada en pedidos de comida. Esta version:

- recibe mensajes desde WhatsApp Cloud API
- guia al cliente durante el pedido
- entiende mensajes mas naturales y puede extraer datos desde texto libre
- calcula un total estimado cuando reconoce productos y cantidades del menu
- redirige con profesionalismo mensajes informales, groseros o mañosos usando un diccionario configurable
- entiende mejor alias, typos y algo de jerga peruana frecuente
- responde dudas operativas del negocio como ubicacion, horarios, delivery y metodos de pago
- usa botones y listas interactivas de WhatsApp para opciones cerradas como delivery, pago y confirmacion
- puede detectar la zona de delivery desde la direccion y aplicar una tarifa por zona
- puede notificar al cliente cuando el pedido cambia a preparando, en camino, entregado o cancelado
- genera un numero de orden unico
- guarda clientes, sesiones y ordenes en SQLite
- notifica al negocio con el resumen de la nueva orden
- permite editar el menu desde API sin tocar codigo

## Flujo actual

1. El cliente escribe por WhatsApp.
2. Aira saluda y pide nombre si aun no lo conoce.
3. Pide el detalle del pedido.
4. Consulta si el pedido es `delivery` o `recojo`.
5. Si es delivery, solicita direccion y referencia.
6. Pregunta el metodo de pago y si necesita vuelto en caso de efectivo.
7. Pide observaciones finales.
8. Resume el pedido con subtotal, delivery y total final, y pide confirmacion.
9. Al confirmar, crea la orden, la guarda y dispara la notificacion al empleado.

## Interaccion guiada

Aira ahora puede usar mensajes interactivos de WhatsApp para que el cliente elija sin escribir todo:

- lista interactiva para elegir productos del menu
- botones para `Delivery` o `Recojo`
- botones para `Efectivo`, `Yape` o `Transferencia`
- botones para confirmar o corregir el pedido
- ubicacion compartida con link de Google Maps para el encargado
- panel con cambio de estados de pedido

Si por algun motivo WhatsApp no acepta el mensaje interactivo, Aira conserva un texto de respaldo para seguir atendiendo.

## Comprension conversacional actual

Aira ya no depende solo de respuestas exactas. Ahora puede:

- detectar nombre si el cliente escribe `soy Carlos`
- detectar pedido si el cliente mezcla productos en una frase libre
- detectar `delivery` o `recojo`
- detectar direccion en mensajes como `Av. Lima 123`
- detectar observaciones como `sin cebolla`
- detectar algunos productos y cantidades del menu para calcular total estimado
- responder preguntas simples sobre menu, horario, delivery, ubicacion y metodos de pago
- pedir solo la informacion que todavia falta

Ejemplo valido:

```text
Hola, soy Carlos y quiero 1 Combo Clasico con 1 Inca Kola para delivery en Av. Lima 123 sin cebolla
```

Aira debe resumir directamente el pedido en vez de volver a preguntar nombre, tipo de entrega o direccion.

Si reconoce correctamente los productos del menu, el resumen tambien mostrara:

- items detectados
- subtotal por item
- delivery
- total final

## Manejo de clientes dificiles

Aira ahora usa un diccionario editable en [src/config/interaction_dictionary.json](C:\Users\Exoni\OneDrive\Documentos\Whastapp proyect\src\config\interaction_dictionary.json) para detectar:

- mensajes informales
- pedidos de fotos
- coqueteo o mensajes mañosos
- groserias leves
- insultos directos
- contenido sexual

La idea es redirigir siempre con profesionalismo hacia el menu, el pedido o la informacion del negocio.

## Diccionario local

Aira ahora usa [src/config/language_dictionary.json](C:\Users\Exoni\OneDrive\Documentos\Whastapp proyect\src\config\language_dictionary.json) para:

- corregir faltas comunes como `hamburgesa`, `gasiosa`, `rekojo`, `delibery`
- mapear alias de productos como `doble`, `gaseosa`, `papitas`, `inca`
- reconocer frases comunes de WhatsApp en Peru como `pa llevar`, `quiero nomas`, `te mando mi ubi`

Tambien puede seguir avanzando con el pedido aunque el cliente aun no haya dado su nombre, y pedirlo despues antes de confirmar.

## Estructura

```text
src/
  api/
  config/
  db/
  models/
  repositories/
  services/
  main.py
```

## Variables de entorno

Copia `.env.example` a `.env` y completa lo necesario.

- `VERIFY_TOKEN`: token usado por Meta para validar el webhook.
- `WHATSAPP_ACCESS_TOKEN`: token de acceso de WhatsApp Cloud API.
- `WHATSAPP_PHONE_NUMBER_ID`: identificador del numero conectado a WhatsApp.
- `WHATSAPP_NOTIFICATION_NUMBER`: numero del empleado o negocio que recibe la notificacion.
- `DATABASE_PATH`: ruta del archivo SQLite.

## Ejecucion local

1. Instala dependencias:

```powershell
py -m pip install -r requirements.txt
```

2. Inicia el servidor:

```powershell
py -m uvicorn src.main:app --reload
```

Si tu Python del sistema no responde, tambien puedes usar el script listo del proyecto:

```powershell
.\start_aira.ps1
```

3. Expone el puerto con tu tunel favorito, por ejemplo `ngrok`.
4. Configura el webhook de Meta apuntando a `/webhooks/whatsapp`.

## Endpoints

- `GET /health`
- `GET /webhooks/whatsapp`
- `POST /webhooks/whatsapp`
- `POST /webhooks/whatsapp/simulate`
- `GET /orders`
- `GET /orders/{order_number}`
- `GET /menu`
- `PUT /menu`

## Prueba rapida sin WhatsApp real

Puedes probar la conversacion localmente con el endpoint de simulacion:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8000/webhooks/whatsapp/simulate" `
  -ContentType "application/json" `
  -Body '{"phone":"+51999999999","message":"hola"}'
```

Luego repite con el mismo telefono:

- `Juan Perez`
- `2 hamburguesas y 1 gaseosa`
- `delivery`
- `Av. Lima 123`
- `sin cebolla`
- `si`

## Actualizar menu

Puedes actualizar el menu con un `PUT /menu`, por ejemplo:

```powershell
Invoke-RestMethod `
  -Method Put `
  -Uri "http://localhost:8000/menu" `
  -ContentType "application/json" `
  -Body '{
    "categories": [
      {
        "name": "Hamburguesas",
        "items": [
          { "name": "Hamburguesa Clasica", "price": 18.0, "is_active": true },
          { "name": "Hamburguesa Doble", "price": 24.0, "is_active": true }
        ]
      },
      {
        "name": "Bebidas",
        "items": [
          { "name": "Gaseosa personal", "price": 5.0, "is_active": true }
        ]
      }
    ]
  }'
```

## Siguiente paso

Cuando tengamos las credenciales reales de Meta, Aira podra enviar y recibir mensajes reales por WhatsApp.
