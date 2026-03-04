from flask import Flask, render_template, request, send_file
from xhtml2pdf import pisa
from io import BytesIO
import base64

app = Flask(__name__)

# Helper function to convert uploaded images to Base64 strings for HTML
def get_base64_image(file_storage):
    if file_storage and file_storage.filename:
        return base64.b64encode(file_storage.read()).decode('utf-8')
    return None

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        # 1. Grab basic form data
        data = {
            'orientation': request.form.get('orientation', 'P'),
            'date': request.form.get('date', ''),
            'bill_no': request.form.get('bill_no', ''),
            'client_address': request.form.get('client_address', '').strip().split('\n'),
            'subject': request.form.get('subject', ''),
            'from_date': request.form.get('from_date', ''),
            'to_date': request.form.get('to_date', ''),
            'company_name': request.form.get('company_name', ''),
            'signer_name': request.form.get('signer_name', ''),
            'columns': request.form.getlist('col_header'),
            'rows': []
        }

        # 2. Parse the dynamic table arrays intelligently
        row_types = request.form.getlist('row_type')
        all_cells = request.form.getlist('cell_value')

        column_count = len(data['columns'])
        cell_iter = iter(all_cells)
        for r_type in row_types:
            if not r_type:
                continue

            if r_type == 'data':
                row_data = [next(cell_iter, "") for _ in range(column_count)]
                data['rows'].append({'type': 'data', 'data': row_data})
            elif r_type == 'total':
                total_value = next(cell_iter, "")
                data['rows'].append({'type': 'total', 'data': [total_value]})

        # 3. Process Images into memory (No saving to disk!)
        header_b64 = get_base64_image(request.files.get('header_img'))
        sig_b64 = get_base64_image(request.files.get('sig_img'))

        # 4. Render HTML template with data
        html_content = render_template('invoice_template.html', data=data, header_b64=header_b64, sig_b64=sig_b64)

        # 5. Convert HTML to PDF entirely in RAM
        pdf_file = BytesIO()
        pisa_status = pisa.CreatePDF(BytesIO(html_content.encode('utf-8')), dest=pdf_file)
        
        if pisa_status.err:
            return "Error creating PDF", 500

        # Rewind memory buffer and send to user
        pdf_file.seek(0)
        filename = request.form.get('filename', 'invoice')
        safe_name = "".join([c for c in filename if c.isalnum() or c in " ._-"])
        
        return send_file(pdf_file, download_name=f"{safe_name}.pdf", as_attachment=True, mimetype='application/pdf')

    # GET request shows the form (bill.html remains exactly the same!)
    return render_template('bill.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
