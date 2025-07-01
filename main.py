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

# Regex: busca entre Ref: y /, o M:xxxx, o 4+ cifras/letras (muy flexible)
REGEX_DEFAULT = r"Ref:\s*([A-Za-z0-9:\.\- ]+?)(?:/|//)|\bM:\d+[A-Z]?\b|\b\d{4,}[A-Z]?\b"

def find_codes(text, regex_pattern):
    # Encuentra TODOS los códigos que matchean el patrón
    codes = []
    for m in re.finditer(regex_pattern, text):
        # Toma el grupo no vacío (por los OR del regex)
        for g in m.groups():
            if g:
                codes.append(g.strip())
    return codes

def highlight_pdf_text(pdf_path, regex_pattern):
    doc = fitz.open(pdf_path)
    found = False
    for page in doc:
        text = page.get_text()
        for match in re.finditer(regex_pattern, text):
            for group in match.groups():
                if group:
                    code = group.strip()
                    areas = page.search_for(code)
                    for area in areas:
                        page.add_highlight_annot(area)
                        found = True
    out_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    doc.save(out_file.name)
    doc.close()
    return out_file.name if found else None

def highlight_image(img, regex_pattern):
    # Usa RGBA para overlay transparente
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
            if t.strip() and code in t:
                (x, y, w, h) = (data['left'][i], data['top'][i], data['width'][i], data['height'][i])
                # Amarillo transparente, borde rojo
                draw.rectangle([(x, y), (x + w, y + h)], fill=(255,255,0,120), outline="red", width=2)
    # Mezcla overlay con original
    img = Image.alpha_composite(img, overlay)
    # Opcional: dibuja lista de códigos al pie
    font = ImageFont.load_default()
    y_text = img.height - 15 * len(codes) - 10
    draw_img = ImageDraw.Draw(img)
    for code in codes:
        draw_img.rectangle([(10, y_text), (img.width - 10, y_text + 15)], fill=(255,255,0,180))
        draw_img.text((15, y_text), code, fill="red", font=font)
        y_text += 15
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
    regex_pattern = request.form.get('regex') or REGEX_DEFAULT

    # Guarda temporalmente
    tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[-1])
    file.save(tmp_file.name)

    ext = file.filename.lower().split('.')[-1]
    try:
        if ext == "pdf":
            try:
                # PDF de texto
                highlighted_pdf = highlight_pdf_text(tmp_file.name, regex_pattern)
                if highlighted_pdf:
                    return send_file(highlighted_pdf, as_attachment=True, download_name="pdf_resaltado.pdf")
            except Exception as e:
                pass  # Si PyMuPDF falla, intentamos imágenes abajo

            # PDF escaneado (como imágenes, OCR)
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
