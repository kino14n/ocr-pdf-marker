from flask import Flask, request, send_file, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

import fitz  # PyMuPDF
from PIL import Image, ImageDraw, ImageFont
import pytesseract
import tempfile
import os
import re
from pdf2image import convert_from_path

# Regex: busca lo que esté entre "Ref:" y la primera / o //
REGEX_DEFAULT = r"Ref:\s*([A-Za-z0-9.\- ]+?)(?:/|//)"

def find_codes(text, regex_pattern):
    # Encuentra TODOS los códigos que matchean el patrón (mayus, minus, puntos, guiones, espacios)
    return [m.group(1).strip() for m in re.finditer(regex_pattern, text)]

def highlight_pdf_text(pdf_path, regex_pattern):
    doc = fitz.open(pdf_path)
    found = False
    for page in doc:
        text = page.get_text()
        for match in re.finditer(regex_pattern, text):
            code = match.group(1)
            areas = page.search_for(code)
            for area in areas:
                page.add_highlight_annot(area)
                found = True
    out_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    doc.save(out_file.name)
    doc.close()
    return out_file.name if found else None

def highlight_image(img, regex_pattern):
    # Realiza OCR a la imagen
    text = pytesseract.image_to_string(img)
    codes = find_codes(text, regex_pattern)
    if not codes:
        return None, []
    # Busca la posición de los códigos y los resalta
    data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
    draw = ImageDraw.Draw(img)
    for i, t in enumerate(data['text']):
        for code in codes:
            if t.strip() and code in t:
                (x, y, w, h) = (data['left'][i], data['top'][i], data['width'][i], data['height'][i])
                draw.rectangle([(x, y), (x + w, y + h)], outline="red", width=2)
                draw.rectangle([(x, y), (x + w, y + h)], fill=(255, 255, 0, 100))  # Amarillo semitransparente
    # Marca los códigos encontrados abajo también (opcional)
    font = ImageFont.load_default()
    y_text = img.height - 15 * len(codes) - 10
    for code in codes:
        draw.rectangle([(10, y_text), (img.width - 10, y_text + 15)], fill="yellow")
        draw.text((15, y_text), code, fill="red", font=font)
        y_text += 15
    tmp_img = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    img.save(tmp_img.name)
    return tmp_img.name, codes

def convert_images_to_pdf(img_paths):
    images = [Image.open(p).convert("RGB") for p in img_paths]
    tmp_pdf = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    images[0].save(tmp_pdf.name, save_all=True, append_images=images[1:])
    for p in img_paths:
        os.remove(p)
    return tmp_pdf.name

@app.route('/resaltar_pdf', methods=['POST'])
def resaltar_pdf():
    if 'file' not in request.files:
        return jsonify({"error": "Archivo no enviado", "status": "error"}), 400

    file = request.files['file']
    regex_pattern = request.form.get('regex') or REGEX_DEFAULT

    # Guarda temporalmente
    tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[-1])
    file.save(tmp_file.name)

    ext = file.filename.lower().split('.')[-1]
    try:
        if ext == "pdf":
            try:
                # ¿PDF de texto?
                highlighted_pdf = highlight_pdf_text(tmp_file.name, regex_pattern)
                if highlighted_pdf:
                    return send_file(highlighted_pdf, as_attachment=True, download_name="pdf_resaltado.pdf")
            except Exception as e:
                pass  # Si PyMuPDF falla, intentamos como imágenes abajo

            # Si no es texto, convierte páginas a imagen y procesa por OCR
            images = convert_from_path(tmp_file.name)
            img_paths = []
            found_any = False
            for img in images:
                img_path = tempfile.NamedTemporaryFile(delete=False, suffix=".png").name
                img.save(img_path)
                out_img, codes = highlight_image(Image.open(img_path), regex_pattern)
                if out_img:
                    img_paths.append(out_img)
                    found_any = True
                else:
                    img_paths.append(img_path)  # Si no hay códigos, igual mete la página original
            if found_any:
                pdf_result = convert_images_to_pdf(img_paths)
                return send_file(pdf_result, as_attachment=True, download_name="pdf_resaltado.pdf")
            else:
                return jsonify({"error": "No se encontraron códigos para resaltar", "status": "error"}), 404

        elif ext in ["jpg", "jpeg", "png"]:
            out_img, codes = highlight_image(Image.open(tmp_file.name), regex_pattern)
            if out_img:
                # Convierte a PDF antes de devolver
                img = Image.open(out_img)
                tmp_pdf = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
                img.convert("RGB").save(tmp_pdf.name)
                return send_file(tmp_pdf.name, as_attachment=True, download_name="pdf_resaltado.pdf")
            else:
                return jsonify({"error": "No se encontraron códigos para resaltar", "status": "error"}), 404

        else:
            return jsonify({"error": "Formato no soportado", "status": "error"}), 400

    except Exception as e:
        return jsonify({"error": f"Error procesando archivo: {str(e)}", "status": "error"}), 500
    finally:
        try:
            os.remove(tmp_file.name)
        except Exception:
            pass

@app.route('/', methods=['GET'])
def health():
    return "OCR PDF Marker running!", 200

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=10000)
