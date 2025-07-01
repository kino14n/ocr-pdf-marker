from flask import Flask, request, send_file, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

import fitz  # PyMuPDF
from PIL import Image, ImageDraw
import pytesseract
import tempfile
import os
import re
from pdf2image import convert_from_path

REGEX_REF = r"Ref:\s*((?:.|\n)*?)(?=/)"  # Acepta saltos de línea

def find_codes(text, regex_pattern=REGEX_REF):
    codes = []
    for m in re.finditer(regex_pattern, text, flags=re.MULTILINE):
        code = m.group(1)
        # Unir fragmentos: quitar saltos de línea y espacios extra
        code = code.replace('\n', '').replace('\r', '').replace(' ', '')
        code = code.strip()
        # Solo códigos razonables
        if code and len(code) >= 3:
            codes.append(code)
    return codes

def highlight_pdf_text(pdf_path, regex_pattern):
    doc = fitz.open(pdf_path)
    found = False
    for page in doc:
        text = page.get_text()
        codes = find_codes(text, regex_pattern)
        for code in codes:
            if not code:
                continue
            areas = page.search_for(code)
            for area in areas:
                page.add_highlight_annot(area)
                found = True
    out_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    doc.save(out_file.name)
    doc.close()
    return out_file.name if found else None

def highlight_image(img, regex_pattern):
    img = img.convert("RGBA")
    text = pytesseract.image_to_string(img)
    codes = find_codes(text, regex_pattern)
    if not codes:
        return None, []
    data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
    overlay = Image.new("RGBA", img.size, (255,255,255,0))
    draw = ImageDraw.Draw(overlay)
    for i, t in enumerate(data['text']):
        for code in codes:
            # Busca coincidencia parcial sin espacios ni saltos
            if t.strip() and t.replace('\n','').replace(' ','') in code.replace(' ',''):
                (x, y, w, h) = (data['left'][i], data['top'][i], data['width'][i], data['height'][i])
                draw.rectangle([(x, y), (x + w, y + h)], fill=(255,255,0,120), outline="red", width=2)
    img = Image.alpha_composite(img, overlay)
    tmp_img = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    img.convert("RGB").save(tmp_img.name)
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
    regex_pattern = REGEX_REF

    tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[-1])
    file.save(tmp_file.name)

    ext = file.filename.lower().split('.')[-1]
    try:
        if ext == "pdf":
            try:
                highlighted_pdf = highlight_pdf_text(tmp_file.name, regex_pattern)
                if highlighted_pdf:
                    return send_file(highlighted_pdf, as_attachment=True, download_name="pdf_resaltado.pdf")
            except Exception as e:
                pass
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
                    img_paths.append(img_path)
            if found_any:
                pdf_result = convert_images_to_pdf(img_paths)
                return send_file(pdf_result, as_attachment=True, download_name="pdf_resaltado.pdf")
            else:
                return jsonify({"error": "No se encontraron códigos para resaltar", "status": "error"}), 404

        elif ext in ["jpg", "jpeg", "png"]:
            out_img, codes = highlight_image(Image.open(tmp_file.name), regex_pattern)
            if out_img:
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
