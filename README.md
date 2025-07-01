# ocr-pdf-marker

Microservicio en Python/Flask que recibe un PDF, extrae texto y resalta los códigos encontrados usando PyMuPDF.  
Ideal para integración con apps web o backend PHP (como InfinityFree).

## Uso

`POST /resaltar_pdf`  
- Form-data:
  - `file`: archivo PDF (obligatorio)
  - `regex`: (opcional) patrón para buscar códigos (por defecto: `Ref:\s*([A-Za-z0-9 .\-]+)[\/]{1,2}`)

## Respuesta

- Descarga directa del PDF resaltado, listo para mostrar o descargar.

## Requisitos

- Python 3.9+
- Flask
- PyMuPDF

## Despliegue recomendado

- [Render.com](https://render.com/)
- Railway
- Google Cloud Run

---
