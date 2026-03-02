from flask import Flask, render_template, request, send_file, jsonify
from fpdf import FPDF
from PIL import Image
import os
import sqlite3

app = Flask(__name__)
# Render uses /tmp for temporary storage
UPLOAD_FOLDER = '/tmp/static_pdfs'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

class BillPDF(FPDF):
    def __init__(self, orientation='P'):
        super().__init__(orientation=orientation, unit='mm', format='A4')
        self.set_auto_page_break(False) 
        
    def footer(self):
        pass

def generate_pdf(data, header_img, sig_img, custom_filename):
    # 1. PAGE SETUP
    orientation = data.get('orientation', 'P')
    pdf = BillPDF(orientation)
    pdf.add_page()
    
    margin = 15
    page_width = 210 if orientation == 'P' else 297
    page_height = 297 if orientation == 'P' else 210
    writable_width = page_width - (2 * margin)
    
    pdf.set_font("Helvetica", size=10)
    
    # 2. HEADER (FULL WIDTH)
    header_bottom_y = margin
    if header_img:
        try:
            with Image.open(header_img) as img:
                w, h = img.size
                aspect = h / w
            render_w = writable_width
            render_h = render_w * aspect
            pdf.image(header_img, x=margin, y=10, w=render_w, h=render_h)
            header_bottom_y = 10 + render_h + 5
        except:
            pass

    pdf.set_y(max(header_bottom_y, 25))
    start_section_y = pdf.get_y()

    # 3. DATE & ADDRESS
    pdf.set_xy(page_width - margin - 80, start_section_y)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(80, 5, f"DATE: {data['date']}", align='R')
    
    pdf.set_xy(margin, start_section_y)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(100, 5, "TO,", ln=1)
    
    raw_addr = data.get('client_address', '').strip()
    if raw_addr:
        if raw_addr.upper().startswith("TO,"): raw_addr = raw_addr[3:].strip()
        elif raw_addr.upper().startswith("TO"): raw_addr = raw_addr[2:].strip()
        
        pdf.set_font("Helvetica", size=10)
        addr_lines = raw_addr.split('\n')[:8]
        for line in addr_lines:
            pdf.set_x(margin)
            pdf.cell(100, 5, line.strip(), ln=1)

    pdf.set_y(max(pdf.get_y(), start_section_y + 20) + 5)

    # 4. SUBJECT, PERIOD, BILL NO
    subject = data.get('subject', '').strip()
    if subject:
        pdf.set_font("Helvetica", "B", 10)
        pdf.multi_cell(0, 5, f"SUB: {subject}", align='C')
    
    f_date = data.get('from_date', '').strip()
    t_date = data.get('to_date', '').strip()
    if f_date or t_date:
        period = f"PERIOD FROM {f_date}"
        if t_date: period += f" TO {t_date}"
        pdf.ln(2)
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 5, period, align='C', ln=1)
        
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 6, f"BILL NO: {data['bill_no']}", align='C', ln=1)
    pdf.ln(5)

    # 5. DYNAMIC TABLE
    columns = data.getlist('col_header')
    if columns:
        row_types = data.getlist('row_type')
        all_cells = data.getlist('cell_value')
        
        # Measure Widths
        pdf.set_font("Helvetica", "B", 9)
        col_max_widths = [pdf.get_string_width(col) + 4 for col in columns]
        
        curr_scan_idx = 0
        pdf.set_font("Helvetica", size=9)
        for r_type in row_types:
            if r_type == 'data':
                for i in range(len(columns)):
                    if curr_scan_idx < len(all_cells):
                        text_val = str(all_cells[curr_scan_idx])
                        w = pdf.get_string_width(text_val) + 4
                        if w > col_max_widths[i]:
                            col_max_widths[i] = w
                        curr_scan_idx += 1
            elif r_type in ['note', 'total']:
                 curr_scan_idx += 1
                 if r_type == 'total': curr_scan_idx += 1

        total_content_width = sum(col_max_widths)
        scale_factor = writable_width / total_content_width
        col_widths = [w * scale_factor for w in col_max_widths]

        # Draw Header
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_fill_color(240, 240, 240)
        for i, col in enumerate(columns):
            pdf.cell(col_widths[i], 8, col, border=1, fill=True, align='C')
        pdf.ln()
        
        # Draw Rows
        curr_idx = 0
        limit_y = page_height - 50 
        
        for r_type in row_types:
            if pdf.get_y() > limit_y: break
                
            if r_type == 'data':
                row_h = 8
                for i in range(len(columns)):
                    val = str(all_cells[curr_idx]) if curr_idx < len(all_cells) else ""
                    pdf.set_font("Helvetica", size=9)
                    while pdf.get_string_width(val) > (col_widths[i] - 1) and pdf.font_size > 6:
                         pdf.set_font("Helvetica", size=pdf.font_size - 0.5)
                    pdf.cell(col_widths[i], row_h, val, border=1, align='C')
                    curr_idx += 1
                pdf.ln()
                
            elif r_type == 'note':
                val = str(all_cells[curr_idx]) if curr_idx < len(all_cells) else ""
                pdf.set_font("Helvetica", "I", 9)
                pdf.cell(writable_width, 8, val, border=1, align='L')
                curr_idx += 1
                pdf.ln()
                
            elif r_type == 'total':
                val = str(all_cells[curr_idx]) if curr_idx < len(all_cells) else ""
                label_w = sum(col_widths[:-1])
                val_w = col_widths[-1]
                
                # FIX: Big Bold Total
                pdf.set_font("Helvetica", "B", 12)
                pdf.cell(label_w, 10, "TOTAL / GRAND TOTAL ", border=1, align='R')
                pdf.cell(val_w, 10, val, border=1, align='R')
                curr_idx += 1
                pdf.ln()

    # 6. SIGNATURE (CENTERED IN 80MM BLOCK)
    pdf.ln(10) 
    if pdf.get_y() > (page_height - 40):
        pdf.add_page()
        
    block_w = 80
    block_x = page_width - margin - block_w
    
    company = data.get('company_name', '')
    if company:
        pdf.set_font("Helvetica", "B", 10)
        prefix = "For " if not company.lower().startswith("for") else ""
        pdf.set_x(block_x)
        pdf.cell(block_w, 5, f"{prefix}{company}", align='C', ln=1)
    
    if sig_img:
        pdf.ln(2)
        sig_w = 40 
        sig_x = block_x + (block_w - sig_w) / 2 
        try:
             current_y = pdf.get_y()
             pdf.image(sig_img, x=sig_x, y=current_y, w=sig_w)
             pdf.set_y(current_y + 15 + 2) 
        except:
             pdf.ln(15)
    else:
        pdf.ln(15)
        
    signer = data.get('signer_name', '')
    if signer:
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_x(block_x)
        pdf.cell(block_w, 5, f"({signer})", align='C', ln=1)

    safe_name = "".join([c for c in custom_filename if c.isalnum() or c in " ._-"])
    output_path = os.path.join(UPLOAD_FOLDER, f"{safe_name}.pdf")
    pdf.output(output_path)
    return output_path

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        if not request.form.get('date') or not request.form.get('bill_no'):
            return "Error: Date and Bill No are required."

        h_file = request.files.get('header_img')
        s_file = request.files.get('sig_img')
        h_path = s_path = None
        
        if h_file and h_file.filename:
            h_path = os.path.join(UPLOAD_FOLDER, "header.jpg")
            h_file.save(h_path)
        if s_file and s_file.filename:
            s_path = os.path.join(UPLOAD_FOLDER, "sig.png")
            s_file.save(s_path)
            
        try:
            pdf_path = generate_pdf(request.form, h_path, s_path, request.form.get('filename', 'bill'))
            return send_file(pdf_path, as_attachment=True)
        except Exception as e:
            return f"Error: {str(e)}"

    return render_template('bill.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
