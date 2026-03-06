from flask import Flask, render_template, request, make_response, jsonify
from weasyprint import HTML

app = Flask(__name__)

# 1. Front-end Route (Loads your form)
@app.route('/')
def index():
    return render_template('bill.html')

# 2. PDF Generation Route (Handles the magic)
@app.route('/generate_pdf', methods=['POST'])
def generate_pdf():
    try:
        # Front-end nunchi vachina JSON data ni capture chesthunnam
        req_data = request.json
        
        # Data, Header Image, and Signature Image ni separate chesthunnam
        data = req_data.get('data', {})
        header_b64 = req_data.get('header_b64', '')
        sig_b64 = req_data.get('sig_b64', '')

        # HTML string ni render chesthunnam (with Jinja variables)
        html_string = render_template(
            'invoice_template.html', 
            data=data, 
            header_b64=header_b64, 
            sig_b64=sig_b64
        )

        # WeasyPrint tho HTML ni PDF ga convert chesthunnam
        pdf_bytes = HTML(string=html_string).write_pdf()

        # Browser ki PDF file laaga pampisthunnam
        response = make_response(pdf_bytes)
        response.headers['Content-Type'] = 'application/pdf'
        
        # File name set chesthunnam (e.g., bill_no_26.pdf)
        bill_no = data.get('bill_no', 'invoice')
        response.headers['Content-Disposition'] = f'inline; filename="bill_no_{bill_no}.pdf"'
        
        return response
        
    except Exception as e:
        # Emaina error vasthe terminal lo print ayyi, browser ki error message velthundi
        print(f"Error generating PDF: {str(e)}")
        return jsonify({'error': 'Failed to generate PDF. Please check server logs.'}), 500

if __name__ == '__main__':
    # Server start chesthunnam
    app.run(debug=True, host='0.0.0.0', port=5000)
