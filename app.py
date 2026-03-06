from flask import Flask, render_template, request, make_response, jsonify
from weasyprint import HTML

app = Flask(__name__)

# Allowed both GET (loading the form) and POST (generating PDF)
@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        try:
            # Getting data from your dynamic frontend
            req_data = request.json
            data = req_data.get('data', {})
            header_b64 = req_data.get('header_b64', '')
            sig_b64 = req_data.get('sig_b64', '')

            # Sending data to HTML template
            html_string = render_template('invoice_template.html', data=data, header_b64=header_b64, sig_b64=sig_b64)
            
            # Generating PDF with WeasyPrint
            pdf_bytes = HTML(string=html_string).write_pdf()

            # Sending PDF back to browser
            response = make_response(pdf_bytes)
            response.headers['Content-Type'] = 'application/pdf'
            
            bill_no = data.get('bill_no', 'invoice') if isinstance(data, dict) else 'invoice'
            response.headers['Content-Disposition'] = f'inline; filename="bill_no_{bill_no}.pdf"'
            return response
            
        except Exception as e:
            print(f"Error generating PDF: {str(e)}")
            return jsonify({'error': 'Failed to generate PDF. Please check server logs.'}), 500

    # If it's a GET request, just show the HTML page
    return render_template('bill.html')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
