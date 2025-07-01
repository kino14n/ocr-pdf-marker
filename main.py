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

# --- Regex robusto: desde Ref: hasta el primer slash (/) ---
REGEX_REF = r"Ref:\s*([A-Za-z0-9:\.\-\s]+?)(?=\/)"

def extract_codes(text):
    # Une los saltos de línea y espacios duplicados
    cleaned = re.sub(r'\s+', ' ', text)
    # Encuentra todos los códigos
    matches = re.findall(REGEX_REF, cleaned)
    results = []
    for m in matches:
        code = m.strip().replace(' ', '').replace('\n', '').replace('\r', '')
        # Opcional: filtra longitud válida y que tenga al menos un número
        if 3 < len(code) < 20 and re.search(r'\d', code):
            results.append(code)
    # Elimina duplicados
    return list(dict.fromkeys(results))

def highlight_pdf_text(pdf_path, regex_pattern):
    doc = fitz.open(pdf_path)
    found = False
    for page in doc:
        # Extrae texto completo y une saltos de línea
        text = page.get_text().replace('\n', ' ')
        codes = extract_codes(text)
        for code in codes:
            # Busca y resalta el código en la página
            areas = page.search_for(code)
            for area in areas:
                page.add_highlight_annot(area)
                found = True
    out_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    doc.save(out_file.name)
    doc.close()
    return out_file.name if found else None

def highlight_image(img, regex_pattern=REGEX_REF):
    img = img.convert("RGBA")
    text = pytesseract.image_to_string(img)
    codes = extract_codes(text)
    if not codes:
        return None, []
    data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
    overlay = Image.new("RGBA", img.size, (255,255,255,0))
    draw = ImageDraw.Draw(overlay)
    for i, t in enumerate(data['text']):
        for code in codes:
            # Si el token del OCR es igual a un código extraído (ignorando espacios)
            if t.strip() and t.replace(' ','') in code.replace(' ',''):
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

    tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[-1])
    file.save(tmp_file.name)

    ext = file.filename.lower().split('.')[-1]
    try:
        if ext == "pdf":
            try:
                highlighted_pdf = highlight_pdf_text(tmp_file.name, REGEX_REF)
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
                out_img, codes = highlight_image(Image.open(img_path))
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
            out_img, codes = highlight_image(Image.open(tmp_file.name))
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
