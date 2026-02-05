from flask import Flask, render_template, request, send_file, jsonify
from fpdf import FPDF
from PIL import Image
import os
import sqlite3

app = Flask(__name__)
UPLOAD_FOLDER = '/tmp/static_pdfs'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
DB_FILE = '/tmp/billcraft_v27_1.db'

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS bills (bill_no TEXT UNIQUE)')
    c.execute('CREATE TABLE IF NOT EXISTS trucks (truck_no TEXT UNIQUE)')
    conn.commit()
    conn.close()

init_db()

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
    
    # Dimensions
    margin = 15
    page_width = 210 if orientation == 'P' else 297
    page_height = 297 if orientation == 'P' else 210
    writable_width = page_width - (2 * margin)
    
    # Font
    pdf.set_font("Helvetica", size=10)
    
    # ==========================================
    # 2. HEADER (Centered, Natural Fit)
    # ==========================================
    header_bottom_y = margin
    if header_img:
        try:
            with Image.open(header_img) as img:
                w, h = img.size
                aspect = h / w
            
            # Smart Fit: Fill width, max height 40mm
            render_w = writable_width
            render_h = render_w * aspect
            if render_h > 40:
                render_h = 40
                render_w = render_h / aspect
            
            x_pos = (page_width - render_w) / 2
            pdf.image(header_img, x=x_pos, y=10, w=render_w, h=render_h)
            header_bottom_y = 10 + render_h + 5
        except:
            pass

    # Start Text Below Header
    pdf.set_y(max(header_bottom_y, 25))
    start_section_y = pdf.get_y()

    # ==========================================
    # 3. DATE & ADDRESS
    # ==========================================
    
    # DATE (Top Right)
    pdf.set_xy(page_width - margin - 80, start_section_y)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(80, 5, f"DATE: {data['date']}", align='R')
    
    # ADDRESS (Top Left)
    pdf.set_xy(margin, start_section_y)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(100, 5, "TO,", ln=1)
    
    raw_addr = data.get('client_address', '').strip()
    if raw_addr:
        if raw_addr.upper().startswith("TO,"): raw_addr = raw_addr[3:].strip()
        elif raw_addr.upper().startswith("TO"): raw_addr = raw_addr[2:].strip()
        
        pdf.set_font("Helvetica", size=10)
        # Limit to 8 lines to prevent overlap
        addr_lines = raw_addr.split('\n')[:8]
        for line in addr_lines:
            pdf.set_x(margin)
            pdf.cell(100, 5, line.strip(), ln=1)

    # Move Cursor Down (Safe Zone)
    pdf.set_y(max(pdf.get_y(), start_section_y + 20) + 5)

    # ==========================================
    # 4. SUBJECT, PERIOD, BILL NO
    # ==========================================
    
    # Subject
    subject = data.get('subject', '').strip()
    if subject:
        pdf.set_font("Helvetica", "B", 10)
        pdf.multi_cell(0, 5, f"SUB: {subject}", align='C')
    
    # Period (Added spacing to prevent "Going Out")
    f_date = data.get('from_date', '').strip()
    t_date = data.get('to_date', '').strip()
    if f_date or t_date:
        period = f"PERIOD FROM {f_date}"
        if t_date: period += f" TO {t_date}"
        pdf.ln(2) # Breathing room
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 5, period, align='C', ln=1)
        
    # Bill No
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 6, f"BILL NO: {data['bill_no']}", align='C', ln=1)
    pdf.ln(5) # Gap before table

    # ==========================================
    # 5. TABLE
    # ==========================================
    columns = data.getlist('col_header')
    if columns:
        row_types = data.getlist('row_type')
        all_cells = data.getlist('cell_value')
        
        col_weights = [len(c) + 2 for c in columns]
        total_w = sum(col_weights)
        col_widths = [(w/total_w) * writable_width for w in col_weights]
        
        # Header
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_fill_color(240, 240, 240)
        for i, col in enumerate(columns):
            pdf.cell(col_widths[i], 8, col, border=1, fill=True, align='C')
        pdf.ln()
        
        # Rows
        pdf.set_font("Helvetica", size=10)
        curr_idx = 0
        limit_y = page_height - 50 # Prevent running off page
        
        for r_type in row_types:
            if pdf.get_y() > limit_y:
                break
                
            if r_type == 'data':
                for i in range(len(columns)):
                    val = str(all_cells[curr_idx]) if curr_idx < len(all_cells) else ""
                    # Auto-Shrink Font
                    pdf.set_font("Helvetica", size=10)
                    while pdf.get_string_width(val) > (col_widths[i] - 2) and pdf.font_size > 7:
                         pdf.set_font("Helvetica", size=pdf.font_size - 0.5)
                    pdf.cell(col_widths[i], 8, val, border=1, align='C')
                    curr_idx += 1
                pdf.ln()
            elif r_type == 'note':
                val = str(all_cells[curr_idx]) if curr_idx < len(all_cells) else ""
                pdf.set_font("Helvetica", "I", 10)
                pdf.cell(writable_width, 8, val, border=1, align='L')
                curr_idx += 1
                pdf.ln()
            elif r_type == 'total':
                val = str(all_cells[curr_idx]) if curr_idx < len(all_cells) else ""
                label_w = sum(col_widths[:-1])
                val_w = col_widths[-1]
                pdf.set_font("Helvetica", "B", 10)
                pdf.cell(label_w, 8, "TOTAL / GRAND TOTAL ", border=1, align='R')
                pdf.cell(val_w, 8, val, border=1, align='R')
                curr_idx += 1
                pdf.ln()

    # ==========================================
    # 6. SIGNATURE (Natural Flow + Gap)
    # ==========================================
    
    # 1. Add your requested GAP (20mm = approx 2cm)
    pdf.ln(20) 
    
    # 2. Check if we fell off the page
    if pdf.get_y() > (page_height - 30):
        pdf.set_y(page_height - 30) # Safety pin to bottom if too long
        
    # 3. Print Signature Block
    pdf.set_font("Helvetica", "B", 10)
    company = data.get('company_name', '')
    if company:
        prefix = "For " if not company.lower().startswith("for") else ""
        pdf.cell(0, 5, f"{prefix}{company}", align='R', ln=1)
        
    if sig_img:
        # Calculate X position (Right Align)
        sig_x = page_width - margin - 40 
        try:
             # Draw image relative to current Y
             pdf.image(sig_img, x=sig_x, y=pdf.get_y()+2, w=40)
             pdf.ln(15) # Move cursor past image
        except:
             pdf.ln(15)
    else:
        pdf.ln(15)
        
    # Name
    signer = data.get('signer_name', '')
    if signer:
        pdf.cell(0, 5, f"({signer})", align='R', ln=1)

    # Output
    safe_name = "".join([c for c in custom_filename if c.isalnum() or c in " ._-"])
    output_path = os.path.join(UPLOAD_FOLDER, f"{safe_name}.pdf")
    pdf.output(output_path)
    return output_path

# --- ROUTES ---
@app.route('/api/trucks')
def get_trucks():
    return jsonify([]) 

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        if not request.form.get('date') or not request.form.get('bill_no'):
            return "Error: Date and Bill No are required."

        h_file = request.files.get('header_img')
        s_file = request.files.get('sig_img')
        h_path = None
        s_path = None
        
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
    app.run(debug=True)
