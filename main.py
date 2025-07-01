from flask import Flask, request, send_file, jsonify
import fitz  # PyMuPDF
import tempfile
import re
import os

app = Flask(__name__)

# Utilidad: resalta todos los códigos en el PDF usando regex
def highlight_codes(pdf_path, regex_pattern):
    doc = fitz.open(pdf_path)
    count = 0
    for page in doc:
        text = page.get_text("text")
        for match in re.finditer(regex_pattern, text):
            codigo = match.group(1)
            instances = page.search_for(codigo)
            for inst in instances:
                # Resalta con amarillo
                page.add_highlight_annot(inst)
                count += 1
    # Guardar resultado temporal
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    doc.save(tmp.name)
    doc.close()
    return tmp.name, count

@app.route('/resaltar_pdf', methods=['POST'])
def resaltar_pdf():
    if 'file' not in request.files:
        return jsonify({'status': 'error', 'error': 'No se recibió archivo'}), 400
    pdf_file = request.files['file']
    if not pdf_file.filename.lower().endswith('.pdf'):
        return jsonify({'status': 'error', 'error': 'Solo se aceptan archivos PDF'}), 400
    regex = request.form.get('regex', r'Ref:\s*([A-Za-z0-9 .\-]+)[\/]{1,2}')
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp:
        pdf_file.save(temp.name)
        out_file, n = highlight_codes(temp.name, regex)
    if n == 0:
        os.remove(out_file)
        return jsonify({'status': 'error', 'error': 'No se encontraron códigos para resaltar'})
    return send_file(out_file, as_attachment=True, download_name="pdf_resaltado.pdf")

@app.route('/')
def home():
    return "Servicio OCR/Resaltado PDF operativo."

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
