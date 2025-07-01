from flask import Flask, request, send_file, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # <-- ¡Debajo de la ÚNICA creación de la app!


import fitz  # PyMuPDF
from PIL import Image, ImageDraw, ImageFont
import pytesseract
import tempfile
import os
import re
from pdf2image import convert_from_path


REGEX_DEFAULT = r"Ref:\s*M?:?\s?([A-Z0-9:\-]+)"

def highlight_pdf_text(pdf_path, regex_pattern):
    doc = fitz.open(pdf_path)
    count = 0
    for page in doc:
        text = page.get_text("text")
        for match in re.finditer(regex_pattern, text):
            codigo = match.group(0)
            # Busca la posición exacta del código en la página
            for inst in page.search_for(codigo):
                page.add_highlight_annot(inst)
                count += 1
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    doc.save(tmp.name)
    doc.close()
    return tmp.name, count

def pdf_has_text(pdf_path):
    try:
        doc = fitz.open(pdf_path)
        for page in doc:
            if page.get_text("text").strip():
                return True
        doc.close()
    except Exception:
        pass
    return False

def highlight_image(img, codes, regex_pattern):
    text = pytesseract.image_to_string(img)
    found_codes = []
    for match in re.finditer(regex_pattern, text):
        code = match.group(0)
        found_codes.append(code)
    # Simplemente marca los códigos al pie de la imagen (no sobre el texto original, pues OCR no da coordenadas)
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    y = img.height - (15 * len(found_codes)) - 10
    for code in found_codes:
        draw.rectangle([(10, y), (img.width - 10, y + 15)], fill="yellow")
        draw.text((15, y), code, fill="red", font=font)
        y += 15
    return img, found_codes

def highlight_pdf_images(pdf_path, regex_pattern):
    images = convert_from_path(pdf_path)
    found_any = []
    temp_images = []
    for img in images:
        img, codes = highlight_image(img, [], regex_pattern)
        found_any.extend(codes)
        temp_img = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        img.save(temp_img.name)
        temp_images.append(temp_img.name)
    # Junta todas las imágenes a un solo PDF
    images = [Image.open(f) for f in temp_images]
    pdf_file = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    images[0].save(pdf_file.name, save_all=True, append_images=images[1:])
    # Limpieza
    for f in temp_images:
        os.remove(f)
    return pdf_file.name, len(found_any)

@app.route('/resaltar_pdf', methods=['POST'])
def resaltar_pdf():
    if 'file' not in request.files:
        return jsonify({'status': 'error', 'error': 'No se recibió archivo'}), 400
    file = request.files['file']
    filename = file.filename.lower()
    regex = request.form.get('regex', REGEX_DEFAULT)

    # Procesar PDF
    if filename.endswith('.pdf'):
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp:
            file.save(temp.name)
            # ¿El PDF tiene texto?
            if pdf_has_text(temp.name):
                out_file, count = highlight_pdf_text(temp.name, regex)
                if count == 0:
                    os.remove(out_file)
                    return jsonify({'status': 'error', 'error': 'No se encontraron códigos para resaltar (PDF con texto)'}), 200
                return send_file(out_file, as_attachment=True, download_name="pdf_resaltado.pdf")
            else:
                # PDF solo imagen: usa OCR
                out_file, count = highlight_pdf_images(temp.name, regex)
                if count == 0:
                    os.remove(out_file)
                    return jsonify({'status': 'error', 'error': 'No se encontraron códigos para resaltar (PDF de imagen)'}), 200
                return send_file(out_file, as_attachment=True, download_name="pdf_resaltado.pdf")

    # Procesar imagen directa (JPG/PNG)
    elif filename.endswith('.jpg') or filename.endswith('.jpeg') or filename.endswith('.png'):
        with tempfile.NamedTemporaryFile(suffix=filename[-4:], delete=False) as temp:
            file.save(temp.name)
            img = Image.open(temp.name)
            img, found_codes = highlight_image(img, [], regex)
            if not found_codes:
                return jsonify({'status': 'error', 'error': 'No se encontraron códigos en la imagen'}), 200
            # Guarda como PDF para entrega uniforme
            pdf_file = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
            img.save(pdf_file.name, "PDF", resolution=100.0)
            return send_file(pdf_file.name, as_attachment=True, download_name="pdf_resaltado.pdf")
    else:
        return jsonify({'status': 'error', 'error': 'Formato no soportado. Sube un PDF o imagen JPG/PNG'}), 400

@app.route('/')
def home():
    return "Servicio OCR/Resaltado PDF e imagen operativo."

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)