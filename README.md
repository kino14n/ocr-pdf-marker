# ocr-pdf-marker

Microservicio universal para resaltar códigos en PDFs y en imágenes usando OCR.

- **Resalta códigos automáticamente en archivos PDF (texto o escaneados) y en imágenes (JPG/PNG)**
- Devuelve un archivo PDF resaltado listo para descargar o mostrar
- Soporta PDFs de solo texto, PDFs escaneados (por OCR) y archivos de imagen
- Ideal para integración con apps web o backend PHP (InfinityFree, etc.)

---

## **¿Cómo funciona?**

1. Envía un archivo (PDF/JPG/PNG) al endpoint `/resaltar_pdf`.
2. El microservicio detecta si es PDF de texto o imagen:
   - **PDF con texto:** busca y resalta códigos directamente.
   - **PDF solo imagen:** extrae cada página como imagen, hace OCR, busca y resalta los códigos.
   - **Imagen (JPG/PNG):** hace OCR, busca y resalta los códigos.
3. Devuelve el PDF resaltado para descarga.

---

## **Uso**

### **POST /resaltar_pdf**

- **Form-data:**
  - `file`: archivo PDF/JPG/PNG (obligatorio)
  - `regex`: patrón opcional para buscar códigos (por defecto: `Ref:\s*M?:?\s?([A-Z0-9:\-]+)`)

#### **Respuesta:**
- Si encuentra códigos:  
  Devuelve el archivo PDF resaltado como descarga.
- Si NO encuentra códigos:  
  Devuelve JSON de error.  
  Ejemplo:  
  ```json
  {"status":"error", "error":"No se encontraron códigos para resaltar"}
