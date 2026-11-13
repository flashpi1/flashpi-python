# Flashpi para Python

SDK oficial de [Flashpi](https://flashpi.com.ec), la API de facturación electrónica del SRI de
Ecuador, para Python.

> **Aún no está publicado en PyPI.** La primera versión (0.1.0) está en preparación. Mientras
> tanto puedes usar la API con HTTP simple: consulta la
> [documentación](https://flashpi.com.ec/docs/).

[English](https://github.com/flashpi1/flashpi-python/blob/main/README.en.md)

- Las 45 operaciones de la API: los seis comprobantes, documentos (XML, RIDE en PDF, correo),
  emisores con establecimientos, puntos de emisión y certificados .p12, webhooks y eventos.
- Un cliente síncrono (`Flashpi`) y uno asíncrono (`AsyncFlashpi`, asyncio) con los mismos
  métodos.
- Tipos (`TypedDict`) generados del documento OpenAPI de la API: tu editor y tu verificador de
  tipos conocen cada campo.
- Reintentos seguros: cada emisión lleva un `Idempotency-Key`, así un reintento nunca emite dos
  veces.
- Errores tipados (RFC 9457) con su `code`, los errores por campo y el `request_id`.
- Paginación automática con `for` y `async for`.
- Verificación de firmas de webhooks (Standard Webhooks) para Django, Flask, FastAPI o cualquier
  framework.
- Python 3.11 o superior. Una sola dependencia: [httpx](https://www.python-httpx.org/).

## Instalación

```bash
pip install flashpi
```

También con `uv add flashpi` o `poetry add flashpi`.

## Primeros pasos

Crea una clave de API en la [consola](https://flashpi.com.ec/app/) y guárdala en la variable de
entorno `FLASHPI_API_KEY`. Una clave `fp_test_` emite en el ambiente de pruebas del SRI; una
`fp_live_` emite comprobantes reales en producción.

```python
from flashpi import Flashpi

# Lee FLASHPI_API_KEY; también puedes pasarla: Flashpi("fp_test_...")
flashpi = Flashpi()

invoice = flashpi.invoices.create(
    {
        "issuerId": "<id del emisor demo o del tuyo>",
        "establishment": "001",
        "emissionPoint": "001",
        "customer": {
            "idType": "ruc",
            "id": "1760013210001",
            "name": "PRUEBAS SERVICIO DE RENTAS INTERNAS",
            "address": "Av. Amazonas y Villalengua, Quito",
        },
        "items": [
            {
                "code": "P-001",
                "description": "Servicio de prueba",
                "quantity": "1",
                "unitPrice": "1.00",
                "taxes": [{"type": "vat", "rate": "15"}],
            }
        ],
        "payments": [{"method": "cash", "amount": "1.15"}],
        "options": {"waitForAuthorization": True},
    }
)

print(invoice["status"], invoice["accessKey"])
```

Las peticiones y las respuestas son diccionarios con las claves de la API, en camelCase
(`invoice["accessKey"]`), tipados con los `TypedDict` de `flashpi.types`
(`from flashpi.types import CreateInvoice, Document`). Los montos y cantidades son **textos**
(`"1.15"`), nunca números, para no perder decimales.

Con el **emisor demo** puedes emitir en pruebas sin subir un certificado: su id está en el
Resumen de la consola (hasta 50 comprobantes al día). Más en
[Sandbox y emisor demo](https://flashpi.com.ec/docs/sandbox/).

Un cliente mantiene un grupo de conexiones: crea uno y reutilízalo. Ciérralo con
`flashpi.close()` o úsalo en un bloque `with`.

## Asíncrono

`AsyncFlashpi` tiene los mismos recursos y métodos; espéralos con `await`.

```python
import asyncio

from flashpi import AsyncFlashpi


async def main() -> None:
    async with AsyncFlashpi() as flashpi:
        status = await flashpi.status.get()
        print(status["status"])

        async for document in flashpi.documents.list({"status": "authorized"}):
            print(document["accessKey"])


asyncio.run(main())
```

Funciona sobre asyncio. Para cancelar una llamada, cancela su tarea (por ejemplo con
`asyncio.timeout()`). Sin `async with`, cierra el cliente con `await flashpi.aclose()`.

## Emitir comprobantes

| Comprobante           | Método                                      |
| --------------------- | ------------------------------------------- |
| Factura               | `flashpi.invoices.create(body)`             |
| Nota de crédito       | `flashpi.credit_notes.create(body)`         |
| Nota de débito        | `flashpi.debit_notes.create(body)`          |
| Liquidación de compra | `flashpi.purchase_settlements.create(body)` |
| Guía de remisión      | `flashpi.waybills.create(body)`             |
| Retención             | `flashpi.withholdings.create(body)`         |

Todos devuelven el documento. Por defecto la respuesta llega enseguida con el estado
`processing` y el resultado del SRI llega por webhook. Con
`"options": {"waitForAuthorization": True}` la API espera la respuesta del SRI (15 s por defecto,
hasta 30 s con `waitTimeoutSeconds`) y devuelve `authorized`, `rejected` o `failed`; si el SRI
tarda más, devuelve `processing` o `pending_sri` y el documento sigue su curso.

## Documentos

```python
from pathlib import Path

document = flashpi.documents.get(invoice["id"])

xml = flashpi.documents.xml(invoice["id"])  # xml["kind"]: "authorized" cuando ya lo autorizó el SRI
pdf = flashpi.documents.pdf(invoice["id"])  # el RIDE, en bytes
Path(f"{invoice['accessKey']}.pdf").write_bytes(pdf)

flashpi.documents.send_email(invoice["id"])  # reenvía RIDE y XML al correo del comprador
```

## Listas y paginación

Una lista devuelve una página. Con `for` recorres todas las páginas, que se piden a medida que
avanzas:

```python
for document in flashpi.documents.list({"status": "authorized", "issueDateFrom": "2026-11-01"}):
    print(document["accessKey"])

page = flashpi.documents.list({"limit": 50})
print(len(page.data))  # los documentos de esta página
if page.has_next_page():
    page = page.next_page()
```

Los filtros usan los nombres de la API (`issueDateFrom`, `issuerId`). Con `AsyncFlashpi`,
`async for` recorre todas las páginas y `await flashpi.documents.list()` devuelve la primera
(`await page.next_page()` la siguiente).

## Errores

Cada error de la API es una subclase de `APIError` según su estado HTTP. Decide según `code`,
que es estable y en inglés; `message` sigue el idioma pedido.

```python
from flashpi import APIError, UnprocessableEntityError

try:
    flashpi.invoices.create(body)
except UnprocessableEntityError as error:
    print(error.code)  # "validation_failed", "total_mismatch", ...
    for field in error.errors:
        print(field["field"], field["message"])
    raise
except APIError as error:
    print(error.status, error.code, error.request_id)  # comparte request_id con soporte
    raise
```

| Clase                      | Estado | Ejemplos de `code`                                          |
| -------------------------- | ------ | ----------------------------------------------------------- |
| `BadRequestError`          | 400    | `malformed_json`, `invalid_idempotency_key`                 |
| `AuthenticationError`      | 401    | `authentication_required`, `invalid_api_key`                |
| `PermissionDeniedError`    | 403    | `key_read_only`, `key_scope_mismatch`, `ip_not_allowed`     |
| `NotFoundError`            | 404    | `not_found`                                                 |
| `ConflictError`            | 409    | `sequential_already_used`, `ride_not_available`             |
| `UnprocessableEntityError` | 422    | `validation_failed`, `total_mismatch`                       |
| `RateLimitError`           | 429    | `demo_issuer_quota_exceeded`, `account_email_limit_reached` |
| `InternalServerError`      | 5xx    | `internal_error`                                            |
| `APIConnectionError`       | —      | sin respuesta (red); `APITimeoutError` si se agotó el plazo |

Todas derivan de `FlashpiError`. Algunos errores traen datos extra en `error.problem`, por
ejemplo `documentId`, `limit`, `resetsAt` o `rideStatus`. Para recibir los mensajes en español:
`Flashpi(language="es")`.

## Reintentos e idempotencia

El SDK reintenta hasta 2 veces, con espera creciente, los errores de red, los tiempos agotados,
las respuestas 408, 429 (si piden esperar 60 s o menos) y 5xx. Cada POST lleva un
`Idempotency-Key` que se repite en sus reintentos, así que la API nunca emite dos veces:

- Si un reintento descubre que el primer intento sí creó el documento, el SDK devuelve ese
  documento.
- Si el primer intento sigue en curso en la API (por ejemplo, se cortó la conexión mientras
  esperaba al SRI), el SDK espera a que termine con la misma clave, hasta el tiempo límite de la
  llamada, sin gastar reintentos.

Para usar tu propia clave (por ejemplo el id de tu pedido), pásala a la llamada:

```python
flashpi.invoices.create(body, idempotency_key=f"pedido-{order.id}")
```

Si una emisión falla igual, el error (un `FlashpiError`) trae la clave que usó en
`error.idempotency_key`. Reintentar con `idempotency_key=error.idempotency_key` nunca emite un
segundo documento: dentro de 24 horas la API devuelve la primera respuesta; después (o si la API
perdió el primer intento), la llamada falla con un 422 `idempotency_key_reused` cuyo
`error.problem["documentId"]` es el documento que ya existe (léelo con `flashpi.documents.get`).

```python
from flashpi import FlashpiError

try:
    flashpi.invoices.create(body)
except FlashpiError as error:
    if error.idempotency_key:
        save_for_retry(body, error.idempotency_key)  # tu cola de reintentos
    raise
```

Una llamada de `AsyncFlashpi` cuya tarea se cancela lanza `asyncio.CancelledError`, que no es un
`FlashpiError` ni trae clave: si cancelas emisiones, pasa tu propio `idempotency_key`.

Los límites diarios (como la cuota del emisor demo) no se reintentan: se lanzan como
`RateLimitError` con `retry_after` en segundos.

## Webhooks

Verifica cada webhook con el cuerpo **tal cual llegó** (sin parsear) y el secreto `whsec_` del
endpoint. `unwrap_webhook` no necesita clave de API (también está en `flashpi.webhooks.unwrap`).
No hace E/S, así que se llama sin `await` también en vistas asíncronas.

Con Django:

```python
import os

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from flashpi import WebhookVerificationError, unwrap_webhook


@csrf_exempt
@require_POST
def flashpi_webhook(request: HttpRequest) -> HttpResponse:
    try:
        event = unwrap_webhook(request.body, request.headers, os.environ["FLASHPI_WEBHOOK_SECRET"])
    except WebhookVerificationError:
        return HttpResponse(status=400)

    if event["type"] == "webhook_endpoint.verification":
        # La activación del endpoint: responde el desafío.
        return JsonResponse({"challenge": event["data"]["challenge"]})
    if event["type"] == "invoice.authorized":
        print("Autorizada", event["data"]["accessKey"])  # event["data"] es el documento
    elif event["type"] == "invoice.rejected":
        print("Rechazada", event["data"]["sriMessages"])
    return HttpResponse(status=204)
```

Con Flask (su `request.headers` no es un `Mapping`, así que pasa `dict(request.headers)`):

```python
import os

from flask import Flask, request

from flashpi import WebhookVerificationError, unwrap_webhook

app = Flask(__name__)


@app.post("/webhooks/flashpi")
def flashpi_webhook():
    try:
        event = unwrap_webhook(
            request.get_data(), dict(request.headers), os.environ["FLASHPI_WEBHOOK_SECRET"]
        )
    except WebhookVerificationError:
        return "", 400

    if event["type"] == "webhook_endpoint.verification":
        return {"challenge": event["data"]["challenge"]}
    handle_event(event)  # tu código, como las ramas del ejemplo de Django
    return "", 204
```

Con FastAPI:

```python
import os

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from flashpi import WebhookVerificationError, unwrap_webhook

app = FastAPI()


@app.post("/webhooks/flashpi")
async def flashpi_webhook(request: Request) -> Response:
    try:
        event = unwrap_webhook(
            await request.body(), request.headers, os.environ["FLASHPI_WEBHOOK_SECRET"]
        )
    except WebhookVerificationError:
        return Response(status_code=400)

    if event["type"] == "webhook_endpoint.verification":
        return JSONResponse({"challenge": event["data"]["challenge"]})
    handle_event(event)  # tu código, como las ramas del ejemplo de Django
    return Response(status_code=204)
```

Guarda el `event["id"]` y descarta los repetidos: un evento puede llegar más de una vez. Durante
una rotación del secreto, Flashpi firma con el nuevo y el anterior, así que cualquiera de los dos
sirve. Si el endpoint usa el modo `thin` (sin `data`), usa
`cast(ThinWebhookEvent, unwrap_webhook(...))` y pide el evento con
`flashpi.events.get(event["id"])`.

## Emisores y certificados

Estas operaciones necesitan una clave de toda la cuenta con acceso de lectura y escritura.

Un emisor nace de su firma electrónica (.p12): Flashpi la verifica, lee el RUC y consulta al SRI,
y te devuelve un `prefill` con lo que encontró para que armes el emisor.

```python
import os
import time
from pathlib import Path

onboarding = flashpi.issuer_onboardings.create(
    {"file": Path("firma.p12").read_bytes(), "password": os.environ["P12_PASSWORD"]}
)
while onboarding["status"] == "verifying":
    time.sleep(2)
    onboarding = flashpi.issuer_onboardings.get(onboarding["id"])
if onboarding["status"] != "ready":
    rejection = onboarding["rejection"]
    raise RuntimeError(rejection["message"] if rejection else onboarding["status"])

prefill = onboarding["prefill"]
if onboarding["existingIssuer"]:
    # Ya tienes ese RUC: el certificado se agrega a ese emisor (una renovación).
    completed = flashpi.issuer_onboardings.complete(onboarding["id"])
else:
    # Un RUC nuevo: tú confirmas los datos del emisor, partiendo del prefill.
    legal_name = prefill and prefill["legalName"]
    address = prefill and prefill["headOfficeAddress"]
    tax_profile = prefill and prefill["taxProfile"]
    rimpe_regime = tax_profile and tax_profile["rimpeRegime"]
    completed = flashpi.issuer_onboardings.complete(
        onboarding["id"],
        {
            "legalName": legal_name or "MI EMPRESA S.A.",
            "headOfficeAddress": address or "Av. Amazonas N24-100, Quito",
            "taxProfile": {
                "keepsAccounting": bool(tax_profile and tax_profile["keepsAccounting"]),
                "rimpeRegime": None if rimpe_regime == "general" else rimpe_regime,
                # Si es contribuyente especial o agente de retención, agrega sus resoluciones.
            },
            # Si onboarding["rucNeedsConfirmation"] es True, envía también "ruc".
        },
    )

for establishment in flashpi.issuers.establishments.list(completed["issuer"]["id"]):
    print(establishment["code"])
```

El `file` puede ser el contenido del .p12 en bytes o un archivo abierto en modo binario
(`open("firma.p12", "rb")`), de hasta 1 MiB.

Para **renovar la firma** de un emisor, para pruebas y producción a la vez, repite el mismo
flujo con el .p12 nuevo: Flashpi reconoce el RUC (`existingIssuer`) y `complete()` sin datos
agrega el certificado. En cambio,
`flashpi.issuers.certificates.upload(issuer_id, {"file": ..., "password": ...})` sube un
certificado solo para el modo de la clave que usas (pruebas o producción).

## Opciones

```python
import os

from flashpi import Flashpi

flashpi = Flashpi(
    api_key=os.environ["FLASHPI_API_KEY"],  # por defecto, la variable FLASHPI_API_KEY
    language="es",  # idioma de los mensajes: "en" (por defecto) o "es"
    timeout=60,  # segundos por intento (el SDK lo amplía al emitir con waitForAuthorization)
    max_retries=2,  # 0 desactiva los reintentos
)
```

Cada método acepta además, como argumentos con nombre, opciones de esa petición:
`idempotency_key`, `timeout`, `max_retries`, `language`, `correlation_id` (tu propio id, que
Flashpi registra) y `extra_headers`.

```python
document = flashpi.documents.get(document_id, timeout=10, language="es", correlation_id="pedido-42")
```

Para ver la respuesta HTTP y el id de la petición, llama al método a través de `with_response`:

```python
result = flashpi.documents.with_response.get(document_id)
print(result.data["status"], result.response.status_code, result.request_id)
```

Para enviar las peticiones con tu propio `httpx.Client` (`httpx.AsyncClient` con `AsyncFlashpi`),
por ejemplo con un proxy o un transporte de pruebas, pásalo en `http_client`. Tú lo cierras; el
SDK nunca sigue redirecciones.

```python
import httpx

from flashpi import Flashpi

flashpi = Flashpi(http_client=httpx.Client(proxy="http://proxy.interno:3128"))
```

En las pruebas, un `httpx.MockTransport` responde en lugar de la API.

## Solo en el servidor

Tu clave de API es secreta: usa el SDK en tus servidores, nunca en código que corre en los
dispositivos de tus usuarios. `repr(flashpi)` muestra el ambiente y la URL, nunca la clave.

## Licencia

[MIT](https://github.com/flashpi1/flashpi-python/blob/main/LICENSE) © 2026 SIGNIADIGITAL S.A.
