from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
import fitz  # PyMuPDF
from PIL import Image, ImageDraw
import pytesseract
import tempfile
import os
import re
from pdf2image import convert_from_path

app = Flask(__name__)
CORS(app)

# PyMuPDF Extraction
def extract_codes_pymupdf(page):
    codes = []
    textblocks = page.get_text("blocks")
    for block in textblocks:
        block_text = block[4]
        # Busca todas las apariciones de 'Ref:'
        for match in re.finditer(r'Ref:(.*?)/', block_text, flags=re.DOTALL):
            code = match.group(1).strip().replace('\n', '').replace('\r', '')
            if code and 2 < len(code) < 30:  # Puedes ajustar el largo
                codes.append(code)
    return codes

def highlight_pdf_with_codes(pdf_path, codes):
    doc = fitz.open(pdf_path)
    found = False
    for page in doc:
        text = page.get_text()
        for code in codes:
            if code in text:
                areas = page.search_for(code)
                for area in areas:
                    page.add_highlight_annot(area)
                    found = True
    out_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    doc.save(out_file.name)
    doc.close()
    return out_file.name if found else None

# OCR Extraction with word grouping
def extract_codes_ocr(img):
    data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
    n = len(data['text'])
    codes = []
    i = 0
    while i < n:
        if data['text'][i].strip() == 'Ref:':
            code_parts = []
            i += 1
            # Une palabras hasta el primer '/' (puede estar separada por OCR)
            while i < n and '/' not in data['text'][i]:
                code_parts.append(data['text'][i])
                i += 1
            if i < n and '/' in data['text'][i]:
                # Si '/' está pegado al código
                word = data['text'][i]
                code_word = word.split('/')[0]
                if code_word:
                    code_parts.append(code_word)
            code = ' '.join(code_parts).replace('\n','').replace('\r','').strip()
            if code and 2 < len(code) < 30:
                codes.append(code)
        i += 1
    return codes

def highlight_image_with_codes(img, codes):
    img = img.convert("RGBA")
    data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
    overlay = Image.new("RGBA", img.size, (255,255,255,0))
    draw = ImageDraw.Draw(overlay)
    for i, t in enumerate(data['text']):
        for code in codes:
            if t.strip() and t.replace('\n',' ').replace(' ','') in code.replace(' ','').replace('\n',''):
                (x, y, w, h) = (data['left'][i], data['top'][i], data['width'][i], data['height'][i])
                draw.rectangle([(x, y), (x + w, y + h)], fill=(255,255,0,120), outline="red", width=2)
    img = Image.alpha_composite(img, overlay)
    tmp_img = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    img.convert("RGB").save(tmp_img.name)
    return tmp_img.name

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
            doc = fitz.open(tmp_file.name)
            all_codes = []
            for page in doc:
                codes = extract_codes_pymupdf(page)
                all_codes.extend(codes)
            doc.close()
            all_codes = list(set(all_codes))  # Únicos
            # Intenta resaltar con los códigos encontrados por PyMuPDF
            if all_codes:
                pdf_res = highlight_pdf_with_codes(tmp_file.name, all_codes)
                if pdf_res:
                    return send_file(pdf_res, as_attachment=True, download_name="pdf_resaltado.pdf")

            # Si no encontró nada, fallback a OCR
            images = convert_from_path(tmp_file.name)
            img_paths = []
            found_any = False
            all_codes_ocr = []
            for img in images:
                codes = extract_codes_ocr(img)
                all_codes_ocr.extend(codes)
                out_img = highlight_image_with_codes(img, codes) if codes else None
                if out_img:
                    img_paths.append(out_img)
                    found_any = True
                else:
                    # Aún así guarda la imagen normal
                    img_path = tempfile.NamedTemporaryFile(delete=False, suffix=".png").name
                    img.save(img_path)
                    img_paths.append(img_path)
            if found_any and all_codes_ocr:
                pdf_result = convert_images_to_pdf(img_paths)
                return send_file(pdf_result, as_attachment=True, download_name="pdf_resaltado.pdf")
            else:
                return jsonify({"error": "No se encontraron códigos para resaltar", "status": "error"}), 404

        elif ext in ["jpg", "jpeg", "png"]:
            img = Image.open(tmp_file.name)
            codes = extract_codes_ocr(img)
            if codes:
                out_img = highlight_image_with_codes(img, codes)
                img2 = Image.open(out_img)
                tmp_pdf = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
                img2.convert("RGB").save(tmp_pdf.name)
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
